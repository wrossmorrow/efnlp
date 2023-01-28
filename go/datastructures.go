package main

import (
	"errors"
	"fmt"
	"os"
	"math/rand"
	"unsafe"

	aws "github.com/aws/aws-sdk-go/aws"
	proto "google.golang.org/protobuf/proto"

	efnlp "github.com/wrossmorrow/efnlp/gen"
)

type TokenType uint32
type ProbType float64

type Language struct {
	size uint32
	ttos map[TokenType]string
	stot map[string]TokenType
}

type Sampler struct {
	total  uint32 // we need to persist this for merge functionality
	counts map[TokenType]uint32
	// counts []ProbType
	// locs   map[TokenType]int // int?
	// toks   map[int]TokenType // int?
}

type SuffixTree struct {
	token    TokenType
	depth    uint32
	sampler  Sampler
	prefixes map[TokenType]SuffixTree
}

type SuffixTreeSet struct {
	size     uint32
	depth    uint32
	prefixes map[TokenType]SuffixTree
}

func (l *Language) FromFileOrS3(
	filename string,
	awsconf *aws.Config,
) error {

	data, err := BytesFromFileOrS3(filename, awsconf)
	if err != nil {
		return err
	}

	lang := &efnlp.Language{}
	if err := proto.Unmarshal(data, lang); err != nil {
		return err
	}
	l.FromProto(lang)

	return nil
}

func (l *Language) FromProto(P *efnlp.Language) error {
	l.size = uint32(len(P.Lang)) // TODO: fix
	l.ttos = make(map[TokenType]string)
	l.stot = make(map[string]TokenType)
	for i := 0; i < len(P.Lang); i++ {
		E := P.Lang[i] // *efnlp.Encoder
		t := TokenType(E.Token)
		c := E.Data
		l.stot[c] = t
		l.ttos[t] = c
	}
	return nil
}

func (l *Language) GetValidText() []string {
	keys := make([]string, len(l.stot))
	i := 0
	for k := range l.stot {
		keys[i] = k
		i++
	}
	return keys
}

func (l *Language) IsValidText(s string) bool {
	_, err := l.Encode(s)
	if err == nil {
		return true
	}
	return false
}

func (l *Language) Encode(s string) ([]TokenType, error) {

	// TODO: need to interpret/generalize to something like a suffix tree
	// (yes, really) to find longest subsequence matches in the passed string

	result := make([]TokenType, len(s)) // TODO: wrong, may not be token/char

	for i, c := range s { // int, rune
		r, ok := l.stot[string(c)]
		if !ok {
			return nil, errors.New("Unknown string encountered")
		}
		result[i] = r
	}

	return result, nil
}

func (l *Language) EncodeProtoPrompt(p *efnlp.Prompt) ([]TokenType, error) {
	// Turn a req.Prompt (protobuf) into a []TokenType

	switch v := p.Value.(type) {

	case *efnlp.Prompt_Text: // string

		result := make([]TokenType, len(v.Text))
		for i, c := range v.Text {
			r, ok := l.stot[string(c)] // l.Encode(string(c))
			if !ok {
				return nil, errors.New("Encountered unknown text (not encodable)")
			}
			result[i] = r
		}
		return result, nil

	case *efnlp.Prompt_Utf8: // []byte

		return nil, errors.New("Encoding UTF8 proto prompts not yet implemented")

	case *efnlp.Prompt_Tokens: // []uint32

		// TODO: UGH. Perhaps just remove TokenType abstraction?
		return *(*[]TokenType)(unsafe.Pointer(&v.Tokens.Tokens[0])), nil

		result := make([]TokenType, len(v.Tokens.Tokens))
		for i, t := range v.Tokens.Tokens {
			result[i] = TokenType(t) // cast from uint32
		}
		return result, nil

	default:
		return nil, errors.New("Unknown prompt type (not text, utf8 bytes, or tokens)")

	}

}

func (l *Language) Decode(seq []TokenType) (string, error) {
	var r string
	for i := 0; i < len(seq); i++ {
		v, ok := l.ttos[seq[i]]
		if !ok {
			return "", errors.New("Invalid token sequence")
		}
		r += v // ok with any language?
	}
	return r, nil
}

func (s *Sampler) EmptyInit() error {
	s.total = 0
	s.counts = make(map[TokenType]uint32)
	return nil
}

func (s *Sampler) FromProto(P *efnlp.Sampler) error {
	s.total = P.Total
	s.counts = make(map[TokenType]uint32)
	for i := 0; i < len(P.Counts); i++ {
		t := TokenType(P.Counts[i].Token)
		c := P.Counts[i].Count
		s.counts[t] = c
	}
	return nil
}

func (s *Sampler) ToProto() *efnlp.Sampler {

	P := efnlp.Sampler{}
	P.Total = s.total
	P.Counts = make([]*efnlp.SamplerTokenCount, len(s.counts))

	i := 0
	for t, c := range s.counts {
		P.Counts[i] = &efnlp.SamplerTokenCount{Token: uint32(t), Count: c}
		i++
	}

	return &P
}

func (s *Sampler) Add(t TokenType) error {
	s.total += 1
	_, exists := s.counts[t]
	if exists {
		s.counts[t] += 1
	} else {
		s.counts[t] = 1
	}
	return nil
}

func (s *Sampler) Sample() (TokenType, error) {

	// Is this actually ok? Can you prove order invariance?
	// That is, we aren't introducing bias in the sampling
	// distribution by have an "unorded" map for counts...
	r := float64(s.total) * rand.Float64()
	for t, c := range s.counts {
		fc := float64(c)
		if r < fc {
			return t, nil
		}
		r -= fc
	}

	// supp R == [0,total], where total == sum(counts), so 
	// if we've subtracted all the counts (`c`) and have not
	// returned already (ie r > 0) there's a problem with the
	// distribution. 
	return TokenType(0), errors.New("Malformed distribution in sampler")
}

func (s *Sampler) Probability(t TokenType) ProbType {
	c, exists := s.counts[t]
	if !exists {
		return ProbType(0.0)
	}
	return ProbType(c) / ProbType(s.total)
}

func (s *SuffixTree) EmptyInit() error {
	// token? 0? not really "accurate"... Don't set here
	s.sampler = Sampler{}
	s.sampler.EmptyInit()
	s.depth = 0
	s.prefixes = make(map[TokenType]SuffixTree)
	return nil
}

func (s *SuffixTree) FromProto(P *efnlp.SuffixTree) error {
	s.token = TokenType(P.Token)
	s.sampler = Sampler{}
	err := s.sampler.FromProto(P.Sampler)
	if err != nil {
		return err
	}
	s.depth = 0
	s.prefixes = make(map[TokenType]SuffixTree)
	for i := 0; i < len(P.Prefixes); i++ {
		T := SuffixTree{}
		err = T.FromProto(P.Prefixes[i])
		if err != nil {
			return err
		}
		s.prefixes[T.token] = T
		s.depth = MaxUInt32(s.depth, T.depth+1)
	}
	return nil
}

func (s *SuffixTree) ToProto() (*efnlp.SuffixTree, error) {
	P := efnlp.SuffixTree{}
	P.Token = uint32(s.token) // ugh
	P.Sampler = s.sampler.ToProto()
	P.Prefixes = make([]*efnlp.SuffixTree, len(s.prefixes))
	i := 0
	for _, T := range s.prefixes {
		Tp, err := T.ToProto() // -> *efnlp.SuffixTree, err
		if err != nil {
			return nil, err
		}
		P.Prefixes[i] = Tp
		i++
	}
	return &P, nil
}

func (s *SuffixTree) Parse(p []TokenType, t TokenType) error {
	s.sampler.Add(t)
	if len(p) == 0 {
		return nil
	}

	l := p[len(p)-1] // "last" token of suffix
	tree, exists := s.prefixes[l]
	if !exists {
		tree = SuffixTree{token: l} // have to set the token...
		tree.EmptyInit()
		s.prefixes[l] = tree
	}
	err := tree.Parse(p[:len(p)-1], t)
	if err != nil {
		return err
	}

	s.depth = MaxUInt32(s.depth, tree.depth+1)
	return nil
}

func (s *SuffixTree) GetDepth() uint32 {
	return s.depth
}

func (s *SuffixTree) Sample(p []TokenType) (TokenType, error) {
	if len(p) == 0 {
		t, err := s.sampler.Sample()
		if err != nil {
			return 0, err
		}
		return t, nil
	}

	t := p[len(p)-1]
	v, ok := s.prefixes[t]
	if !ok {
		t, err := s.sampler.Sample()
		if err != nil {
			return 0, err
		}
		return t, nil
	}

	return v.Sample(p[:len(p)-1])
}

func (s *SuffixTreeSet) EmptyInit() error {
	s.size = 0
	s.depth = 0
	s.prefixes = make(map[TokenType]SuffixTree)
	return nil
}

func (s *SuffixTreeSet) FromFileOrS3(
	filename string,
	awsconf *aws.Config,
) error {

	data, err := BytesFromFileOrS3(filename, awsconf)
	if err != nil {
		return err
	}

	sfxs := &efnlp.SuffixTreeSet{}
	if err := proto.Unmarshal(data, sfxs); err != nil {
		return err
	}
	s.FromProto(sfxs)

	return nil
}

func (s *SuffixTreeSet) FromProto(P *efnlp.SuffixTreeSet) error {
	s.size = uint32(len(P.Prefixes))
	s.depth = 0
	s.prefixes = make(map[TokenType]SuffixTree)
	for i := 0; i < len(P.Prefixes); i++ {
		T := SuffixTree{}
		err := T.FromProto(P.Prefixes[i])
		if err != nil {
			return err
		}
		s.prefixes[T.token] = T
		s.depth = MaxUInt32(s.depth, T.depth+1)
	}
	return nil
}

func (s *SuffixTreeSet) ToProto() (*efnlp.SuffixTreeSet, error) {
	P := efnlp.SuffixTreeSet{}
	P.Prefixes = make([]*efnlp.SuffixTree, len(s.prefixes))
	i := 0
	for _, T := range s.prefixes {
		Tp, err := T.ToProto() // -> *efnlp.SuffixTree, err
		if err != nil {
			return nil, err
		}
		P.Prefixes[i] = Tp
		i++
	}
	return &P, nil
}

func (s *SuffixTreeSet) Parse(p []TokenType, t TokenType) error {
	if len(p) == 0 {
		return errors.New("cannot parse an empty prefix")
	}
	l := p[len(p)-1] // "last" token of prefix
	tree, exists := s.prefixes[l]
	if !exists {
		tree = SuffixTree{token: l} // have to set the token...
		tree.EmptyInit()
		s.prefixes[l] = tree
	}
	err := tree.Parse(p[:len(p)-1], t)
	if err != nil {
		return err
	}
	s.depth = MaxUInt32(s.depth, tree.depth+1)
	return nil
}

func (s *SuffixTreeSet) GetDepth() uint32 {
	return s.depth
}

func (s *SuffixTreeSet) Sample(prompt []TokenType) (TokenType, error) {
	if len(prompt) == 0 {
		// could sample tokens from raw occurrence frequencies
		return 0, errors.New("Sampling requires a (nontrivial) prefix")
	}

	token := prompt[len(prompt)-1]
	prefix, ok := s.prefixes[token]
	if !ok {
		return 0, errors.New(
			fmt.Sprintf("Unknown token (%d) in prefix", token),
		)
		// NOTE: when distributing control this could happen? like a 404
	}

	return prefix.Sample(prompt[:len(prompt)-1])
}

func (s *SuffixTreeSet) Generate(
	size uint32,
	blockSize uint32,
	prompt []TokenType,
) ([]TokenType, error) {

	result := make([]TokenType, size)

	i := uint32(0)

	for ; i < uint32(len(prompt)); i++ {
		result[i] = prompt[i]
	}

	for ; i < blockSize; i++ {
		t, err := s.Sample(result[:i])
		if err != nil {
			return result, err
		}
		result[i] = t
	}

	for ; i < size; i++ {
		t, err := s.Sample(result[i-blockSize : i])
		if err != nil {
			return result, err
		}
		result[i] = t
	}

	return result, nil

}

type EFNLPParser struct{
	Lang *Language
	Trees *SuffixTreeSet
}

func (P *EFNLPParser) Parse(tokseq []TokenType, blockSize int, verbose bool) {

	P.Trees = &SuffixTreeSet{}
	P.Trees.EmptyInit()

	// enumerate block-size-long sequences, parsing each with it's successor
	for i := blockSize ; i < len(tokseq)-1 ; i++ {
		P.Trees.Parse(tokseq[i-blockSize:i], tokseq[i])
	}

}

func (P *EFNLPParser) Dump(out string, compress bool) error {

	Pp, err := P.Trees.ToProto()
	if err != nil {
		return err
	}

	data, err := proto.Marshal(Pp) // data []byte
    if err != nil {
    	return err
    }

    // compress with gzip 
    if compress {
    	gz, err := GzBytes(data) // gz []byte
    	if err != nil {
    		return err
    	}
    	err = os.WriteFile(out, gz, 0644)    
    } else {
    	err = os.WriteFile(out, data, 0644)
    }

    if err != nil {
    	return err
    }
	return nil

}

