package main

import (
	// "bytes"
	"fmt"
	"log"
	"math"
	"math/rand"
	"os"
	"testing"
	"time"
)

// var buf bytes.Buffer
// log.SetOutput(&buf)
// defer func() {
// 	log.SetOutput(os.Stderr)
// }()

// ...

// T.Log(buf.String())

func RandToken(T int) TokenType {
	return TokenType(math.Floor(float64(T) * rand.Float64()))
}

func coveringCorpus(T int) []TokenType {
	C := make([]TokenType, 10*T)
	for i := 0; i < 10*T; i++ {
		C[i] = RandToken(T)
	}
	return C
}

func TestParsingIsCompleteAbstract(T *testing.T) {

	var tests = []struct {
		L int
		B int
	}{
		{10, 3},
		{50, 5},
		{100, 10},
		{1000, 10},
		{10000, 10},
	}

	for _, tt := range tests {
		tn := fmt.Sprintf("(%d,%d)", tt.L, tt.B)
		T.Run(tn, func(T *testing.T) {

			L := tt.L
			B := tt.B

			C := coveringCorpus(L)
			N := len(C)

			S := &SuffixTreeSet{}
			S.EmptyInit()
			err := S.ParseAll(C, B)
			if err != nil {
				T.Errorf("Failed to parse: %v", err)
			}

			// all B-element subsequences can be matched in the parsed tree
			for i := B; i < N-1; i++ {
				if !S.Match(C[i-B : i]) {
					log.Printf("Failed to match: %d, %d, %v", i-B, i, C[i-B:i])
					T.Errorf("Failed to match: %v", C[i-B:i])
				}
			}

			// all B-or-less element subsequences have a positive probability
			for i := B; i < N; i++ {
				for j := 0; j < B; j++ {
					p := C[i-B+j : i]
					t := C[i]
					P, err := S.Probability(p, t)
					if err != nil {
						T.Errorf("Failed to match %v -> %d at %d/%d: %v", p, t, i, N, err)
					}
					if P == 0 {
						T.Errorf("Failed to match %v -> %d at %d/%d (probability zero)", p, t, i, N)
					}
				}
			}

			// TODO: examine the reverse: any prefix in the

		})
	}

}

func TestParsingIsCompleteCorpus(T *testing.T) {

	var tests = []struct {
		Language  string
		Filename  string
		BlockSize int
	}{
		{"../test/unit/data/shakes.json", "../data/tinywillspeare.txt", 10},
		{"../test/unit/data/gpt-2.json", "../data/tinywillspeare.txt", 10},
	}

	for _, tt := range tests {
		tn := fmt.Sprintf("(%s,%s)", tt.Language, tt.Filename)
		T.Run(tn, func(T *testing.T) {

			data, err := os.ReadFile(tt.Language)
			if err != nil {
				T.Fatalf("Error reading content: %v", err)
			}

			L := &Language{}
			err = L.FromEncoderOnlyJson(data)
			if err != nil {
				T.Fatalf("Error reading content: %v", err)
			}

			data, err = os.ReadFile(tt.Filename)
			if err != nil {
				T.Fatalf("Error reading \"%s\": %v", tt.Filename, err)
			}

			text := string(data)

			start := time.Now()
			C, err := L.Encode(text, false)
			if err != nil {
				T.Fatalf("Error while encoding text: \"%v\"", err)
			}
			duration_ms := time.Since(start).Milliseconds()
			log.Printf("Encoded %d tokens in %d ms", len(C), duration_ms)

			// TEMPORARY
			counts := make(map[int]int)
			for _, token := range C {
				s, _ := L.DecodeOne(token) // ignore error
				l := len(s)
				_, exists := counts[l]
				if exists {
					counts[l] += 1
				} else {
					counts[l] = 1
				}
			}
			for size, count := range counts {
				log.Printf("counted %d %d-element strings", count, size)
			}

			N := len(C)
			B := tt.BlockSize

			start = time.Now()
			S := &SuffixTreeSet{}
			S.EmptyInit()
			err = S.ParseAll(C, B)
			if err != nil {
				T.Errorf("Failed to parse: %v", err)
			}
			duration_ms = time.Since(start).Milliseconds()
			log.Printf("Parsed in %d ms", duration_ms)

			// all B-element subsequences can be matched in the parsed tree
			for i := B; i < N-1; i++ {
				if !S.Match(C[i-B : i]) {
					T.Errorf("Failed to match: %v", C[i-B:i])
				}
			}

			// all B-or-less element subsequences have a positive probability
			for i := B; i < N; i++ {
				for j := 0; j < B; j++ {
					p := C[i-B+j : i]
					t := C[i]
					P, err := S.Probability(p, t)
					if err != nil {
						T.Errorf("Failed to match %v -> %d at %d/%d: %v", p, t, i, N, err)
					}
					if P == 0 {
						T.Errorf("Failed to match %v -> %d at %d/%d (probability zero)", p, t, i, N)
					}
				}
			}

			// TODO: examine the reverse: any prefix in the

		})
	}

}
