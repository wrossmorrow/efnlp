package main

import (
	// "bytes"
	"log"
	"os"

	"fmt"

	"testing"
)

// var buf bytes.Buffer
// log.SetOutput(&buf)
// defer func() {
// 	log.SetOutput(os.Stderr)
// }()

// ...

// T.Log(buf.String())

func TestSuffixEncoderToFromJson(T *testing.T) {

	E := &SuffixEncoder{}

	b, err := E.ToJson()
	if err != nil {
		T.Errorf("Failed to serialize JSON: \"%v\"", err)
	}

	F := &SuffixEncoder{}
	err = F.FromJson(b)
	if err != nil {
		T.Errorf("Failed to deserialize from JSON: \"%v\"", err)
	}

	if F.Value != E.Value {
		T.Errorf("Equality failed (value): %c vs %c", F.Value, E.Value)
	}
	if F.Depth != E.Depth {
		T.Errorf("Equality failed (depth): %d vs %d", F.Depth, E.Depth)
	}
	if F.Token != E.Token {
		T.Errorf("Equality failed (token): %d vs %d", F.Token, E.Token)
	}
	if F.Atom != E.Atom {
		T.Errorf("Equality failed (atom): %t vs %t", F.Atom, E.Atom)
	}

}

func TestSuffixEncoderToFromProto(T *testing.T) {

	E := &SuffixEncoder{}

	P := E.ToProto()

	F := &SuffixEncoder{}
	err := F.FromProto(P)
	if err != nil {
		T.Errorf("Failed to deserialize from Proto: \"%v\"", err)
	}

	if F.Value != E.Value {
		T.Errorf("Equality failed (value): %c vs %c", F.Value, E.Value)
	}
	if F.Depth != E.Depth {
		T.Errorf("Equality failed (depth): %d vs %d", F.Depth, E.Depth)
	}
	if F.Token != E.Token {
		T.Errorf("Equality failed (token): %d vs %d", F.Token, E.Token)
	}
	if F.Atom != E.Atom {
		T.Errorf("Equality failed (atom): %t vs %t", F.Atom, E.Atom)
	}

}

func TestSuffixEncoderDefine(T *testing.T) {

	var tests = []struct {
		Value    rune
		Prefixes map[TokenType][]rune
		Invalid  []rune
	}{
		{
			'a',
			map[TokenType][]rune{
				TokenType(1): []rune{'a'},
				TokenType(2): []rune{'b'},
				TokenType(3): []rune{'c'},
			},
			[]rune{'z'},
		},
		{
			'\u0120',
			map[TokenType][]rune{
				TokenType(1): []rune{'a'},
				TokenType(2): []rune{'b'},
				TokenType(3): []rune{'c'},
			},
			[]rune{'z'},
		},
	}

	for _, tt := range tests {
		tn := fmt.Sprintf("%c", tt.Value)
		T.Run(tn, func(T *testing.T) {

			v := tt.Value
			E := &SuffixEncoder{}
			E.ForValue(v)

			for t, q := range tt.Prefixes {

				// p := append(q, v) // <q>v
				d := E.Define(q, t)
				if int(d) != len(q) {
					T.Errorf("Depth invalid after define: %d vs %d", d, len(q))
				}

				enc := E.Encode(q)
				if !enc.Valid {
					T.Errorf("Encode valid failed: %v", enc)
				}
				if enc.Token != t {
					T.Errorf("Encode token failed: expected %d got %d", t, enc.Token)
				}

			}

			enc := E.Encode(tt.Invalid)
			if enc.Valid {
				T.Errorf("Encode failed to fail on \"%c\": %v", tt.Invalid, enc)
			}

		})
	}

}

// The tests below include some failure cases for pure forward/prefix
// and backward/suffix search in a tokenizing encoding.
//
// The real issue though is whether any "Language" more "advanced"
// than unicode characters (a flat tree) is worthwhile at all.
// There is probably a place for common character pairs, like "th"
// and "gh" or affective endings like "ing" or "ion" etc. But
// some patterns, particularly _repeated_ characters, are efficient
// but perhaps not _effective_?
//
// To the degree that the language itself, in terms of it's character
// clusters encoded into tokens, is more verbose then it is playing
// a larger role in modeling the language to begin with. In other
// words, by choosing a tokenization that effectively represents
// important "phonemes", words, or expressions then that is doing some
// heavy lifting for grammatical modeling.
//
// But, the OpenAI encoder has some seemingly "absurd" clusters, such
// as
//
// 	'ÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤ
//	 ÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤÃĥÃĤ'
//
// and many words like
//
//	'ĠUniversity'
//
// which (up to the 'Ġ' prefix) suggests some common words themselves
// are tokenized. (Oddly, ' ' and '\n' aren't in the GPT-2 encoder,
// but we've added them here.)

func TestLanguageDefine(T *testing.T) {

	var tests = []struct {
		Lang map[string]TokenType
	}{
		{
			map[string]TokenType{
				"a": TokenType(0),
				"b": TokenType(1),
				"c": TokenType(2),
			},
		},
		{
			map[string]TokenType{
				"aa": TokenType(0),
				"ab": TokenType(1),
				"a":  TokenType(2),
				"b":  TokenType(3),
			},
		},
		// The following is a failure case for forwards prefix search.
		{
			map[string]TokenType{
				"aa": TokenType(0),
				"ab": TokenType(1),
				"a":  TokenType(2),
			},
		},
		// The following is a failure case for backwards suffix search.
		{
			map[string]TokenType{
				"aa": TokenType(0),
				"ba": TokenType(1),
				"a":  TokenType(2),
			},
		},
		{
			map[string]TokenType{
				"aaa": TokenType(0),
				"aab": TokenType(1),
				"ab":  TokenType(2),
				"a":   TokenType(3),
				"b":   TokenType(4),
			},
		},
		{
			map[string]TokenType{
				"\u0120gazed": TokenType(0),
				"\u0120":      TokenType(1),
				"g":           TokenType(2),
				"a":           TokenType(3),
				"z":           TokenType(4),
				"e":           TokenType(5),
				"d":           TokenType(6),
			},
		},
	}

	for i, tt := range tests {
		tn := fmt.Sprintf("case %d", i)
		T.Run(tn, func(T *testing.T) {

			L := &Language{}

			for p, t := range tt.Lang {
				err := L.Define(p, t)
				if err != nil {
					T.Errorf("Error while defining language at (%s, %d): \"%v\"", p, t, err)
				}
			}

			if int(L.Size) != len(tt.Lang) {
				T.Errorf("Defined language has an inconsistent size (%d vs %d)", L.Size, len(tt.Lang))
			}

			for p, t := range tt.Lang {
				ts, err := L.Encode(p, false)
				if err != nil {
					T.Errorf("Error while encoding \"%s\": \"%v\"", p, err)
					b, _ := L.ToJson()
					T.Errorf("JSON: %s", b)
				}
				if len(ts) != 1 || ts[0] != t {
					T.Errorf("Encoding \"%s\" invalid after define: expected %d got %v", p, t, ts)
					s, _ := L.Decode(ts)
					T.Errorf("Decoding would yield: \"%s\"", s)
				}
			}

			for p, t := range tt.Lang {
				s, err := L.Decode([]TokenType{t})
				if err != nil {
					T.Errorf("Error while decoding %d language: \"%v\"", t, err)
				}
				if s != p {
					T.Errorf("Decoding invalid after define: expected \"%s\" got %v", p, s)
				}
			}

			C := coveringCorpus(len(tt.Lang))
			corpus, _ := L.Decode(C)
			_, err := L.Encode(corpus, false)
			if err != nil {
				T.Errorf("Error while encoding sampled corpus: \"%v\"", err)
			}

		})
	}

}

func TestLanguageReadJSON(T *testing.T) {

	var tests = []struct {
		Filename string
	}{
		{"../test/unit/data/shakes.json"},
		{"../test/unit/data/gpt-2.json"},
		{"../test/unit/data/wiki.json"},
	}

	for _, tt := range tests {
		tn := fmt.Sprintf("case[%s]", tt.Filename)
		T.Run(tn, func(T *testing.T) {

			data, err := os.ReadFile(tt.Filename)
			if err != nil {
				T.Fatalf("Error reading content: %v", err)
			}

			L := &Language{}
			err = L.FromEncoderOnlyJson(data)
			if err != nil {
				T.Fatalf("Error reading content: %v", err)
			}

			log.Printf("%s stats: %d tokens, %d level deep tree; %dB", tt.Filename, L.Size, L.Depth, L.Memory())

		})
	}

}

func TestEncodeDecodeFile(T *testing.T) {

	var tests = []struct {
		Filename string
	}{
		{"../data/tinywillspeare.txt"},
	}

	for _, tt := range tests {
		tn := fmt.Sprintf("case[%s]", tt.Filename)
		T.Run(tn, func(T *testing.T) {

			data, err := os.ReadFile(tt.Filename)
			if err != nil {
				T.Fatalf("Error reading \"%s\": %v", tt.Filename, err)
			}

			text := string(data)
			utext := []rune(text)

			D := make(map[string]TokenType)
			C := TokenType(0)
			for _, r := range utext {
				c := string(r)
				_, exists := D[c]
				if !exists {
					D[c] = C
					C += 1
				}
			}

			L := &Language{}
			for c, t := range D {
				err := L.Define(c, t)
				if err != nil {
					T.Errorf("Error while defining language at (%s, %d): \"%v\"", c, t, err)
				}
			}

			encoded, err := L.Encode(text, false)
			if err != nil {
				T.Errorf("Error while encoding text: \"%v\"", err)
			}

			recoded, err := L.Decode(encoded)
			if err != nil {
				T.Errorf("Error while decoding token sequence: \"%v\"", err)
			}

			if recoded != text {
				T.Errorf("Error recovering text...")
			}

		})
	}

}
