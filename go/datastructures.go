package main

import (
	"errors"
	// "context"
	// "io/ioutil"
	// "log"
	// "sync"
	"math/rand"
	"unsafe"

	"crypto/sha1"
	// "golang.org/x/crypto/blake2b"
	"encoding/hex"

	// "google.golang.org/protobuf/proto"

	efnlp "github.com/wrossmorrow/efnlp/gen"
)

type TokenType uint32
type ProbType float64

func hashUTF8(str []byte) string {
	// h := blake2b.Sum256(str) // longer strings; faster?
	h := sha1.Sum(str)
	return hex.EncodeToString(h[:])
}

type Language struct {
	size int32 // uint32
	ttos map[TokenType]string
	stot map[string]TokenType
}

type Sampler struct {
	total  ProbType
	counts []ProbType
	locs   map[TokenType]int // int?
	toks   map[int]TokenType // int?
}

type SuffixTree struct {
	token    TokenType
	sampler  Sampler
	prefixes map[TokenType]SuffixTree
}

type SuffixTreeSet struct {
	size     int32 // uint32
	prefixes map[TokenType]SuffixTree
}

func (l *Language) Initialize(P *efnlp.Language) error {
	l.size = int32(len(P.Lang)) // TODO: fix
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

	// for i := 0 ; i < len(s) ; i++ {
	//     h := hashUTF8(str[i:i+1])
	//     r, ok := l.stot[h]
	//     if !ok {
	//         return nil, errors.New("Unknown string encountered")
	//     }
	//     result[i] = r
	// }

	return result, nil
}

func (l *Language) EncodeProtoPrompt(p *efnlp.Prompt) ([]TokenType, error) {
	// Turn a req.Prompt into a []TokenType

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

func (s *Sampler) Initialize(P *efnlp.Sampler) error {
	s.total = 1.0 // TODO: abstracted type safe?
	s.counts = make([]ProbType, len(P.Data))
	s.locs = make(map[TokenType]int)
	s.toks = make(map[int]TokenType)
	for i := 0; i < len(P.Data); i++ {
		t := TokenType(P.Data[i].Token)
		p := ProbType(P.Data[i].Prob)
		s.counts[i] = p
		s.locs[t] = i
		s.toks[i] = t
	}
	return nil
}

func (s *Sampler) Sample() (TokenType, error) {
	r := ProbType(rand.Float64())
	for i := 0; i < len(s.counts); i++ {
		if r < s.counts[i] {
			return s.toks[i], nil
		}
		r -= s.counts[i]
	}
	return TokenType(0), errors.New("Malformed distribution in sampler")
}

func (s *Sampler) Probability(t TokenType) ProbType {
	idx, ok := s.locs[t]
	if !ok {
		return ProbType(0.0)
	}
	return s.counts[idx] / s.total
}

func (s *SuffixTree) Initialize(P *efnlp.SuffixTree) error {
	s.token = TokenType(P.Token)
	s.sampler = Sampler{}
	s.sampler.Initialize(P.Sampler)
	s.prefixes = make(map[TokenType]SuffixTree)
	for i := 0; i < len(P.Prefixes); i++ {
		T := SuffixTree{}
		T.Initialize(P.Prefixes[i])
		s.prefixes[T.token] = T
	}
	return nil
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

func (s *SuffixTreeSet) Initialize(P *efnlp.SuffixTreeSet) error {
	s.size = int32(len(P.Prefixes))
	s.prefixes = make(map[TokenType]SuffixTree)
	for i := 0; i < len(P.Prefixes); i++ {
		T := SuffixTree{}
		T.Initialize(P.Prefixes[i])
		s.prefixes[T.token] = T
	}
	return nil
}

func (s *SuffixTreeSet) Sample(prompt []TokenType) (TokenType, error) {
	if len(prompt) == 0 {
		// could sample tokens from raw occurrence frequencies
		return 0, errors.New("Sampling requires a (nontrivial) prefix")
	}

	token := prompt[len(prompt)-1]
	prefix, ok := s.prefixes[token]
	if !ok {
		return 0, errors.New("Unknown token in prefix")
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
