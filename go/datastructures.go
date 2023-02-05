package main

import (
	"encoding/json"
	"errors"
	"fmt"
	// "log"
	"math/rand"
	"os"
	"reflect"
	"strings"
	// "unsafe"

	aws "github.com/aws/aws-sdk-go/aws"
	proto "google.golang.org/protobuf/proto"

	pb "github.com/wrossmorrow/efnlp/gen"
)

type ValueType rune
type TokenType uint16
type ProbType float64

type _Encoder struct {
	Token TokenType
	Valid bool
	Depth uint32
}

type SuffixEncoder struct {
	Value    rune                    `json:"value"` // native UTF-8 strings
	Depth    uint32                  `json:"depth"`
	Token    TokenType               `json:"token"`
	Atom     bool                    `json:"atom"`
	Prefixes map[rune]*SuffixEncoder `json:"prefixes"`
}

type Language struct {
	Name     string                  `json:"name"`
	Size     TokenType               `json:"size"` // max token "index"
	Depth    uint32                  `json:"depth"`
	Suffixes map[rune]*SuffixEncoder `json:"suffixes"`
	Decoder  map[TokenType]string    `json:"decoder"`
	// TODO: if we can assert contiguity, decoder is an array!
}

type Sampler struct {
	total  uint32 // we need to persist this for merge functionality
	counts map[TokenType]uint32
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

func (e *SuffixEncoder) FromProto(P *pb.SuffixEncoder) error {
	utf8value := []rune(P.Value)
	// assert len(utf8value) == 1
	e.Value = utf8value[0] // proto has UTF-8 strings
	e.Depth = P.Depth
	e.Token = TokenType(P.Token)
	e.Atom = P.Atom

	e.Prefixes = make(map[rune]*SuffixEncoder)
	for i := 0; i < len(P.Prefixes); i++ {
		E := &SuffixEncoder{}
		E.FromProto(P.Prefixes[i])
		e.Prefixes[E.Value] = E
	}

	return nil
}

func (e *SuffixEncoder) ToProto() *pb.SuffixEncoder {
	P := pb.SuffixEncoder{}
	P.Value = string(e.Value)
	P.Depth = e.Depth // is a uint32
	P.Token = uint32(e.Token)
	P.Atom = e.Atom

	i := 0
	for _, E := range e.Prefixes {
		P.Prefixes[i] = E.ToProto()
		i++
	}
	return &P
}

func (e *SuffixEncoder) FromJson(data []byte) error {
	return json.Unmarshal(data, e)
}

func (e *SuffixEncoder) ToJson() ([]byte, error) {
	return json.Marshal(*e)
}

func (e *SuffixEncoder) ForValue(v rune) {
	e.Value = v
	e.Depth = 0
	e.Token = TokenType(0)
	e.Atom = false
	e.Prefixes = make(map[rune]*SuffixEncoder)
}

func (e *SuffixEncoder) Memory() uintptr {
	m := reflect.TypeOf(e.Value).Size()
	m += reflect.TypeOf(e.Depth).Size()
	m += reflect.TypeOf(e.Token).Size()
	m += reflect.TypeOf(e.Atom).Size()
	for v, E := range e.Prefixes {
		m += reflect.TypeOf(v).Size() + E.Memory()
	}
	return m
}

func (e *SuffixEncoder) Define(p []rune, t TokenType) uint32 {
	if len(p) == 0 {
		e.Token = t
		e.Atom = true
		return 0
	}
	v := p[len(p)-1]
	E, exists := e.Prefixes[v]
	if !exists {
		E = &SuffixEncoder{}
		E.ForValue(v)
		e.Prefixes[v] = E
	}
	d := E.Define(p[:len(p)-1], t) + 1
	if d > e.Depth {
		e.Depth = d
	}
	return e.Depth
}

func (e *SuffixEncoder) Encode(p []rune) _Encoder {
	if len(p) == 0 || len(e.Prefixes) == 0 {
		return _Encoder{e.Token, e.Atom, 1}
	}
	v := p[len(p)-1]
	E, exists := e.Prefixes[v]
	if !exists {
		return _Encoder{e.Token, e.Atom, 1}
	}
	r := E.Encode(p[:len(p)-1])
	if r.Valid {
		r.Depth += 1
		return r
	}
	return _Encoder{e.Token, e.Atom, 1}
}

func (e *SuffixEncoder) Decoder() map[TokenType][]rune {
	// TODO: figure out the less wasteful method, passing the map
	// and suffixes down the tree
	d := make(map[TokenType][]rune)
	if e.Atom {
		d[e.Token] = []rune{e.Value}
	}
	for _, E := range e.Prefixes {
		D := E.Decoder()
		for t, u := range D {
			// TODO: verify non existence?
			d[t] = append(u, e.Value)
		}
	}
	return d
}

// Note: decodes are pre-processed lookups in a map held by Language
// Don't need to traverse suffix tree to decode token sequences

func (l *Language) FromFileOrS3(filename string, conf *aws.Config) error {
	data, err := BytesFromFileOrS3(filename, conf)
	if err != nil {
		return err
	}
	l.FromProtoBytes(data)
	return nil
}

func (l *Language) FromProtoBytes(data []byte) error {
	lang := &pb.Language{}
	if err := proto.Unmarshal(data, lang); err != nil {
		return err
	}
	l.FromProto(lang)
	return nil
}

func (l *Language) FromProto(P *pb.Language) error {
	// TODO: version
	// TODO: options
	l.Name = P.Name
	l.Size = TokenType(P.Stats.Size)
	l.Depth = P.Stats.Depth
	l.Suffixes = make(map[rune]*SuffixEncoder)
	l.Decoder = make(map[TokenType]string)
	for i := 0; i < len(P.Suffixes); i++ {
		E := &SuffixEncoder{}
		E.FromProto(P.Suffixes[i])
		l.Suffixes[E.Value] = E
		D := E.Decoder()
		for t, u := range D {
			// TODO: assert non-existence of t?
			l.Decoder[t] = string(u) // convert from []rune
		}
	}
	return nil
}

func (l *Language) ToProto() *pb.Language {
	P := pb.Language{}
	P.Name = l.Name
	// version, options
	P.Stats.Size = uint32(l.Size)
	P.Stats.Depth = l.Depth
	i := 0
	for _, e := range l.Suffixes {
		P.Suffixes[i] = e.ToProto()
		i++
	}
	return &P
}

func (l *Language) FromJson(data []byte) error {
	return json.Unmarshal(data, l)
}

func (l *Language) ToJson() ([]byte, error) {
	return json.Marshal(*l)
}

func (l *Language) FromEncoderOnlyJson(data []byte) error {
	// Define a Language from a "TokenEncoder" style map in JSON
	// For example, see OpenAI's "gpt-2.json" in the python tests data.
	D := make(map[string]int)
	err := json.Unmarshal(data, &D)
	if err != nil {
		return err
	}
	for s, t := range D {
		T := TokenType(t) // TODO: assert validity of uint16 or whatever
		err = l.Define(s, T)
		if err != nil {
			return err
		}
	}
	return nil
}

func (l *Language) ToEncoderOnlyJson() ([]byte, error) {
	// Basically reverse the Decoder field. See also GetTokenEncoder
	E := make(map[string]int)
	for t, s := range l.Decoder {
		E[s] = int(t)
	}
	return json.Marshal(E)
}

func (l *Language) Memory() uintptr {
	m := reflect.TypeOf(l.Size).Size()
	m += reflect.TypeOf(l.Depth).Size()
	for v, E := range l.Suffixes {
		m += reflect.TypeOf(v).Size() + E.Memory()
	}
	for t, s := range l.Decoder {
		m += reflect.TypeOf(t).Size() + uintptr(len(s))*reflect.TypeOf(s).Size()
	}
	return m
}

// Language: primary methods for defining, encoding and decoding

func (l *Language) Define(s string, t TokenType) error {
	if len(s) == 0 {
		return errors.New("Cannot define an empty string")
	}
	if l.Suffixes == nil {
		l.Suffixes = make(map[rune]*SuffixEncoder)
	}
	if l.Decoder == nil {
		l.Decoder = make(map[TokenType]string)
	}
	// set in decoder; TODO: verify non-existence
	l.Decoder[t] = s
	if t+1 > l.Size { // don't subtract from a uint16(0)
		l.Size = t + 1 // NOTE: not verifying contiguity
	}
	u := []rune(s) // convert to codepoint-aware array (copy?)
	v := u[len(u)-1]
	e, exists := l.Suffixes[v]
	if !exists {
		e = &SuffixEncoder{}
		e.ForValue(v)
		l.Suffixes[v] = e
	}
	d := e.Define(u[:len(u)-1], t) + 1
	if d > l.Depth {
		l.Depth = d
	}
	return nil
}

func (l *Language) Encode(s string, ignoreErrors bool) ([]TokenType, error) {

	uchars := []rune(s)                      // Convert to codepoints; TODO: is this a copy?
	result := make([]TokenType, len(uchars)) // TODO: wrong, may not be token/uchar

	// if we don't really have a tree, short circuit parsing with
	// a simpler (and maybe even a little bit faster) method.
	if l.Depth == 1 {
		for i, r := range uchars {
			S, exists := l.Suffixes[r]
			if !exists {
				if ignoreErrors {
					// TODO: check language for a replacement strategy
				} else {
					return nil, errors.New(
						fmt.Sprintf("Unencodable UTF-8 codepoint \"%c\" (%x) encountered", r, r),
					)
				}
			} else {
				result[i] = S.Token
			}
		}
		return result, nil
	}

	C := len(uchars) - 1
	for i := C; i >= 0; {
		r := uchars[i]
		e, exists := l.Suffixes[r]
		if exists {
			E := e.Encode(uchars[:i])
			// assert E.Valid?
			result[C] = E.Token
			i -= int(E.Depth) // from uint32; TODO: why absorb cast cost here? Just let depth be int?
			C -= 1
		} else {
			if ignoreErrors {
				i -= 1
			} else {
				err := errors.New(
					fmt.Sprintf("Unencodable UTF-8 codepoint \"%c\" (%x) encountered", r, r),
				)
				return nil, err
			}
		}
	}

	if C < 0 {
		return result, nil
	}
	return result[C+1:], nil
}

func (l *Language) DecodeOne(t TokenType) (string, error) {
	s, ok := l.Decoder[t]
	if !ok {
		return "", errors.New(
			fmt.Sprintf("Invalid token (%d) encountered", t),
		)
	}
	return s, nil
}

func (l *Language) Decode(seq []TokenType) (string, error) {
	// Decode uses a plain map; encoding is the "hard" part requiring
	// tree traversal... but we have to arrange to have a reasonable
	// lack of copies in the strings formed (especially at "scale";
	// even 1MB is slow with naive appends). We use a memory-efficient
	// "StringBuilder" (go 1.10+) to accomplish this.
	//
	// E.g., consider naive code:
	//
	//	r := "" // plain intialization
	//	for i := 0; i < len(seq); i++ {
	//		v, ok := l.Decoder[seq[i]]
	//		if !ok {
	//			...
	//		}
	//		r += v // TODO: LOTS of copies; likely very memory inefficient
	//	}
	//	return r, nil
	//
	// This can take a minute or more to decode 1MB worth of tokens. The
	// StringBuilder approach takes an unnoticable fraction of a second.
	var B strings.Builder
	for i := 0; i < len(seq); i++ {
		s, ok := l.Decoder[seq[i]]
		if !ok {
			return "", errors.New(
				fmt.Sprintf("Invalid token (%d) encountered", seq[i]),
			)
		}
		B.WriteString(s)
	}
	return B.String(), nil
}

// Language: aliases only

func (l *Language) Tokenize(s string, ignoreErrors bool) ([]TokenType, error) {
	return l.Encode(s, ignoreErrors)
}

func (l *Language) Render(seq []TokenType) (string, error) {
	return l.Decode(seq)
}

// Language: Simple getters, and routines useful in a gRPC service

func (l *Language) GetTokenEncoder() map[string]TokenType {
	// Just invert the map Decoder; we don't store this but can
	// easily supply it. (The reason we don't store it is because
	// with a Suffix-based language we wouldn't know which key
	// to look up.) This is really just a convenience method.
	enc := make(map[string]TokenType)
	for t, s := range l.Decoder {
		enc[s] = t
	}
	return enc
}

func (l *Language) GetValidText() []string {
	// Just get the values list of the map Decoder.
	keys := make([]string, len(l.Decoder))
	i := 0
	for _, s := range l.Decoder {
		keys[i] = s
		i++
	}
	return keys
}

func (l *Language) IsValidText(s string) bool {
	// Just try to encode without ignoring errors
	_, err := l.Encode(s, false)
	if err == nil {
		return true
	}
	return false
}

func (l *Language) EncodeProtoPrompt(p *pb.Prompt) ([]TokenType, error) {
	// Turn a req.Prompt (protobuf) into a []TokenType

	switch v := p.Value.(type) {

	case *pb.Prompt_Tokens: // []uint32

		// TODO: UGH. Perhaps just remove TokenType abstraction?
		// This could _actually_ be unsafe (corrupting) if we can't
		// read uints of the same bytewidth.
		// return *(*[]TokenType)(unsafe.Pointer(&v.Tokens.Tokens[0])), nil

		result := make([]TokenType, len(v.Tokens.Tokens))
		for i, t := range v.Tokens.Tokens {
			result[i] = TokenType(t) // cast from uint32
		}
		return result, nil

	case *pb.Prompt_Text: // string
		return l.Encode(v.Text, false)

	case *pb.Prompt_Utf8: // []byte
		return nil, errors.New("Encoding UTF8 proto prompts not yet implemented")

	default:
		return nil, errors.New("Unknown prompt type (not text, utf8 bytes, or tokens)")

	}

}

func (s *Sampler) EmptyInit() error {
	s.total = 0
	s.counts = make(map[TokenType]uint32)
	return nil
}

func (s *Sampler) FromProto(P *pb.Sampler) error {
	s.total = P.Total
	s.counts = make(map[TokenType]uint32)
	for i := 0; i < len(P.Counts); i++ {
		t := TokenType(P.Counts[i].Token)
		c := P.Counts[i].Count
		s.counts[t] = c
	}
	return nil
}

func (s *Sampler) ToProto() *pb.Sampler {

	P := pb.Sampler{}
	P.Total = s.total
	P.Counts = make([]*pb.SamplerTokenCount, len(s.counts))

	i := 0
	for t, c := range s.counts {
		P.Counts[i] = &pb.SamplerTokenCount{Token: uint32(t), Count: c}
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

func (s *Sampler) Probability(t TokenType) float64 {
	c, exists := s.counts[t]
	if !exists {
		return 0.0
	}
	return float64(c) / float64(s.total)
}

func (s *SuffixTree) EmptyInit() error {
	// token? 0? not really "accurate"... Don't set here
	s.sampler = Sampler{}
	s.sampler.EmptyInit()
	s.depth = 0
	s.prefixes = make(map[TokenType]SuffixTree)
	return nil
}

func (s *SuffixTree) FromProto(P *pb.SuffixTree) error {
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

func (s *SuffixTree) ToProto() (*pb.SuffixTree, error) {
	P := pb.SuffixTree{}
	P.Token = uint32(s.token) // ugh
	P.Sampler = s.sampler.ToProto()
	P.Prefixes = make([]*pb.SuffixTree, len(s.prefixes))
	i := 0
	for _, T := range s.prefixes {
		Tp, err := T.ToProto() // -> *pb.SuffixTree, err
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

func (s *SuffixTree) Match(p []TokenType) bool {
	if len(p) == 0 {
		return false
	}
	t, exists := s.prefixes[p[len(p)-1]]
	if !exists {
		return false
	}
	if len(p) == 1 {
		return true
	}
	return t.Match(p[:len(p)-1])
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

func (s *SuffixTree) Probability(p []TokenType, t TokenType) float64 {
	if len(p) == 0 {
		return s.sampler.Probability(t)
	}
	P, exists := s.prefixes[p[len(p)-1]]
	if !exists {
		return s.sampler.Probability(t)
	}
	return P.Probability(p[:len(p)-1], t)
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

	sfxs := &pb.SuffixTreeSet{}
	if err := proto.Unmarshal(data, sfxs); err != nil {
		return err
	}
	s.FromProto(sfxs)

	return nil
}

func (s *SuffixTreeSet) FromProto(P *pb.SuffixTreeSet) error {
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

func (s *SuffixTreeSet) ToProto() (*pb.SuffixTreeSet, error) {
	P := pb.SuffixTreeSet{}
	P.Prefixes = make([]*pb.SuffixTree, len(s.prefixes))
	i := 0
	for _, T := range s.prefixes {
		Tp, err := T.ToProto() // -> *pb.SuffixTree, err
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

func (s *SuffixTreeSet) ParseAll(p []TokenType, b int) error {
	for i := 1; i < b; i++ {
		err := s.Parse(p[0:i], p[i])
		if err != nil {
			return err
		}
	}
	for i := b; i < len(p); i++ {
		err := s.Parse(p[i-b:i], p[i])
		if err != nil {
			return err
		}
	}
	return nil
}

func (s *SuffixTreeSet) GetDepth() uint32 {
	return s.depth
}

func (s *SuffixTreeSet) Match(p []TokenType) bool {
	if len(p) == 0 {
		return false
	}
	t, exists := s.prefixes[p[len(p)-1]]
	if !exists {
		return false
	}
	if len(p) == 1 {
		return true
	}
	return t.Match(p[:len(p)-1])
}

func (s *SuffixTreeSet) Sample(p []TokenType) (TokenType, error) {
	if len(p) == 0 {
		// could sample tokens from raw occurrence frequencies
		return 0, errors.New("Sampling requires a (nontrivial) prefix")
	}
	t := p[len(p)-1]
	P, exists := s.prefixes[t]
	if !exists {
		return 0, errors.New(
			fmt.Sprintf("Unknown token (%d) in prefix", t),
		)
		// NOTE: when distributing control this could happen? like a 404
	}
	return P.Sample(p[:len(p)-1])
}

func (s *SuffixTreeSet) Probability(p []TokenType, t TokenType) (float64, error) {
	if len(p) == 0 {
		// could sample tokens from raw occurrence frequencies
		return 0, errors.New("Not using raw occurrence counts yet")
	}
	P, exists := s.prefixes[p[len(p)-1]]
	if !exists {
		return 0, errors.New("Not found, not using raw occurrence counts yet")
	}
	return P.Probability(p[:len(p)-1], t), nil
}

func (s *SuffixTreeSet) Generate(
	size int,
	blockSize int,
	prompt []TokenType,
) ([]TokenType, error) {

	result := make([]TokenType, size)

	i := 0

	for ; i < len(prompt); i++ {
		result[i] = prompt[i]
	}

	if len(prompt) < blockSize {
		// sample up to blocksize as the prompt header doesn't
		// cover this many tokens. this may be the noisiest part
		// of generation. 
		for ; i < blockSize; i++ {
			t, err := s.Sample(result[:i])
			if err != nil {
				return result, err
			}
			result[i] = t
		}
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

type EFNLPParser struct {
	Lang  *Language
	Trees *SuffixTreeSet
}

func (P *EFNLPParser) Parse(tokseq []TokenType, blockSize int, verbose bool) {

	P.Trees = &SuffixTreeSet{}
	P.Trees.EmptyInit()

	// enumerate block-size-long sequences, parsing each with it's successor
	for i := blockSize; i < len(tokseq)-1; i++ {
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
