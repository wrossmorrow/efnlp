package main

import (
	"context"
	"fmt"
	"io/ioutil"
	"log"
	"time"

	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
	proto "google.golang.org/protobuf/proto"

	efnlp "github.com/wrossmorrow/efnlp/gen"
)

const blockSize = 10

func MaxInt(a int, b int) int {
	if a <= b {
		return b
	}
	return a
}

type EFNLPServiceConfig struct {
	languageFilename string
	modelFilename    string
	verbose          bool
}

type EFNLPService struct { // implements gen/service_grpc.pg.go::GenerationServer

	config   *EFNLPServiceConfig
	language *Language      // *efnlp.Language
	model    *SuffixTreeSet // *efnlp.SuffixTreeSet

	efnlp.UnimplementedGenerationServer
	// GetValidText(context.Context, *GetValidTextRequest) (*GetValidTextResponse, error)
	// IsValidText(context.Context, *IsValidTextRequest) (*IsValidTextResponse, error)
	// GenerateBatch(context.Context, *GenerateBatchRequest) (*GenerateBatchResponse, error)
	// GenerateStream(*GenerateStreamRequest, Generation_GenerateStreamServer) error
	// mustEmbedUnimplementedGenerationServer()

}

func (s *EFNLPService) Initialize(verbose bool) error {
	// NOTE: need the pointer receiver to persist initialization
	// of language and model into struct we will actually serve

	{

		in, err := ioutil.ReadFile(s.config.languageFilename)
		if err != nil {
			log.Fatalf("Error reading language file: %v", err)
		}

		lang := &efnlp.Language{}
		if err := proto.Unmarshal(in, lang); err != nil {
			log.Fatalf("Failed to parse language: %v", err)
		}

		s.language = &Language{}
		s.language.Initialize(lang)

		if verbose {
			log.Println("Read language into memory")
			// log.Printf("Language: %v", s.language)
		}

	} // TODO: verify efnlp.Language is deallocated after

	{

		in, err := ioutil.ReadFile(s.config.modelFilename)
		if err != nil {
			log.Fatalf("Error reading model file: %v", err)
		}

		mdl := &efnlp.SuffixTreeSet{}
		if err := proto.Unmarshal(in, mdl); err != nil {
			log.Fatalf("Failed to parse model: %v", err)
		}

		s.model = &SuffixTreeSet{}
		s.model.Initialize(mdl)

		if verbose {
			log.Printf("Read model into memory")
		}

	} // TODO: verify efnlp.SuffixTreeSet is deallocated after

	return nil
}

func (s EFNLPService) GetValidText(
	ctx context.Context,
	req *efnlp.GetValidTextRequest,
) (*efnlp.GetValidTextResponse, error) {

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	keys := s.language.GetValidText() // []string; could we pass in reference to resp.Text?
	resp := efnlp.GetValidTextResponse{}
	resp.Text = make([]string, len(keys))
	i := 0
	for _, key := range keys {
		resp.Text[i] = key
		i++
	}
	return &resp, nil
}

func (s EFNLPService) IsValidText(
	ctx context.Context,
	req *efnlp.IsValidTextRequest,
) (*efnlp.IsValidTextResponse, error) {

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	return &efnlp.IsValidTextResponse{
		Text:  req.Text,
		Valid: s.language.IsValidText(req.Text),
	}, nil

}

func (s EFNLPService) GetModelBlockSize(
	ctx context.Context,
	req *efnlp.GetModelBlockSizeRequest,
) (*efnlp.GetModelBlockSizeResponse, error) {

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	return &efnlp.GetModelBlockSizeResponse{
		Size: blockSize,
	}, nil

}

func (s EFNLPService) GenerateBatch(
	ctx context.Context,
	req *efnlp.GenerateBatchRequest,
) (*efnlp.GenerateBatchResponse, error) {

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	var i uint32
	resp := efnlp.GenerateBatchResponse{
		Prompt:    req.Prompt,
		BatchSize: req.BatchSize,
		Samples:   req.Samples,
	}

	p, err := s.language.EncodeProtoPrompt(req.Prompt)
	if err != nil {
		err := status.Error(
			codes.NotFound,
			"Some text in the prompt was not found",
		)
		return nil, err
	}

	if req.Instrument {

		stats := efnlp.Statistics{}
		for i = 0; i < req.Samples; i++ {
			start := time.Now()
			seq, err := s.model.Generate(req.BatchSize, blockSize, p) // []TokenType
			if err != nil {
				err := status.Error(
					codes.Internal,
					"There was an unexpected issue generating text",
				)
				return nil, err
			}
			gen, err := s.language.Decode(seq) // string
			if err != nil {

			}
			stats.GenTimeNs += time.Since(start).Nanoseconds()
			resp.Result = append(resp.Result, gen) // []string
		}
		stats.GenFreqNs = float64(stats.GenTimeNs) / float64(req.BatchSize*req.Samples)
		resp.Stats = &stats

	} else {

		for i = 0; i < req.Samples; i++ {
			seq, err := s.model.Generate(req.BatchSize, blockSize, p) // []TokenType
			if err != nil {
				err := status.Error(
					codes.Internal,
					"There was an unexpected issue generating text",
				)
				return nil, err
			}
			gen, err := s.language.Decode(seq) // string
			if err != nil {

			}
			resp.Result = append(resp.Result, gen) // []string
		}

	}

	return &resp, nil
}

func (s EFNLPService) GenerateStream(
	req *efnlp.GenerateStreamRequest,
	stream efnlp.Generation_GenerateStreamServer,
) error {

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	// grpc uses one goroutine per method call, so we don't
	// have to explicitly manage concurrency here

	p, err := s.language.EncodeProtoPrompt(req.Prompt) // p []TokenType
	if err != nil {
		err := status.Error(
			codes.NotFound,
			"Some text in the prompt was not found",
		)
		return err
	}

	if req.Instrument {

		for i := uint32(0); i < req.MaxBatches; i++ {

			stats := efnlp.Statistics{}
			start := time.Now()
			seq, err := s.model.Generate(req.BatchSize, blockSize, p) // []TokenType
			if err != nil {
				err := status.Error(
					codes.Internal,
					"There was an unexpected issue generating text",
				)
				return err
			}
			fp := MaxInt(len(p), blockSize)
			gen, err := s.language.Decode(seq[fp:]) // string
			if err != nil {

			}
			stats.GenTimeNs += time.Since(start).Nanoseconds()
			stats.GenFreqNs = float64(stats.GenTimeNs) / float64(req.BatchSize)

			resp := efnlp.GenerateStreamResponse{Result: gen, Stats: &stats}
			if err := stream.Send(&resp); err != nil {
				log.Printf("send error %v", err)
			}

			p = seq[len(seq)-blockSize : len(seq)]

		}

	} else {

		for i := uint32(0); i < req.MaxBatches; i++ {
			seq, err := s.model.Generate(req.BatchSize, blockSize, p) // []TokenType
			if err != nil {
				err := status.Error(
					codes.Internal,
					"There was an unexpected issue generating text",
				)
				return err
			}
			fp := MaxInt(len(p), blockSize)
			gen, err := s.language.Decode(seq[fp:]) // string
			if err != nil {

			}
			resp := efnlp.GenerateStreamResponse{Result: gen}
			if err := stream.Send(&resp); err != nil {
				log.Printf("send error %v", err)
			}

			p = seq[len(seq)-blockSize : len(seq)]

		}

	}

	return nil

}
