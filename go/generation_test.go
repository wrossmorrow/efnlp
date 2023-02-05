package main

import (
	// "bytes"
	"fmt"
	"log"
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

func TestGenerationAbstract(T *testing.T) {

	var tests = []struct {
		L int
		B int
		G int
	}{
		{10, 3, 1000},
		{50, 5, 1000},
		{100, 10, 1000},
		{1000, 10, 1000},
		{10000, 10, 1000},
	}

	for _, tt := range tests {
		tn := fmt.Sprintf("(%d,%d,%d)", tt.L, tt.B, tt.G)
		T.Run(tn, func(T *testing.T) {

			L := tt.L
			B := tt.B
			G := tt.G

			C := coveringCorpus(L)

			S := &SuffixTreeSet{}
			S.EmptyInit()
			err := S.ParseAll(C, B)
			if err != nil {
				T.Errorf("Failed to parse: %v", err)
			}

			ts, err := S.Generate(G, B, []TokenType{0})
			if err != nil {
				T.Errorf("Failed to generate: %v", err)
			}
			if len(ts) < G {
				T.Errorf("Failed to generate all requested: %d vs %d", len(ts), G)
			}

		})
	}

}

func TestGenerationCorpus(T *testing.T) {

	var tests = []struct {
		Name string
		Language  string
		Filename  string
		BlockSize int
		Generate  int
	}{
		{"shakes-speare", "../test/unit/data/shakes.json", "../data/tinywillspeare.txt", 10, 10000},
		{"gpt-2-speare", "../test/unit/data/gpt-2.json", "../data/tinywillspeare.txt", 10, 10000},
		{"shakes-speare", "../test/unit/data/shakes.json", "../data/tinywillspeare.txt", 20, 10000},
		{"gpt-2-speare", "../test/unit/data/gpt-2.json", "../data/tinywillspeare.txt", 20, 10000},
	}

	for _, tt := range tests {

		tn := fmt.Sprintf("(%s,%s,%d,%d)", tt.Language, tt.Filename, tt.BlockSize, tt.Generate)
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
			log.Printf("Encoded in %d ms", duration_ms)

			B := tt.BlockSize
			G := tt.Generate

			start = time.Now()
			S := &SuffixTreeSet{}
			S.EmptyInit()
			err = S.ParseAll(C, B)
			if err != nil {
				T.Errorf("Failed to parse: %v", err)
			}
			duration_ms = time.Since(start).Milliseconds()
			log.Printf("Parsed in %d ms", duration_ms)

			ts, err := S.Generate(G, B, []TokenType{0})
			if err != nil {
				T.Errorf("Failed to generate: %v", err)
			}

			generated, err := L.Decode(ts)
			if err != nil {
				T.Errorf("Failed to decode generated: %v", err)
			}

			out := fmt.Sprintf("results/tests/%s-%d-%d.txt", tt.Name, tt.BlockSize, tt.Generate)
		    f, err := os.Create(out)
		    if err != nil {
				T.Fatalf("Failed to open file \"%s\": %v", out, err)
		    }
		    defer f.Close()

		    _, err = f.WriteString(generated)
		    if err != nil {
				T.Errorf("Failed to write generated text to file \"%s\": %v", out, err)
		    }

		})
	}

}
