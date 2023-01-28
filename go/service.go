package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"

	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"

	efnlp "github.com/wrossmorrow/efnlp/gen"
)

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

	if strings.HasSuffix(s.config.languageFilename, "/") {
		return errors.New("Filenames can't end with \"/\"")
	}

	// if languageFilename starts with s3:// ... assume
	// passed string is like
	//
	//      s3://{bucket}[/{prefix}]/{filename}
	//
	// and we need to download and store in `filename`

	s.language = &Language{}
	err := s.language.FromFileOrS3(s.config.languageFilename, nil)
	if err != nil {
		log.Fatalf("Failed to parse language: %v", err)
	}

	if verbose {
		log.Println("Read language into memory")
		// log.Printf("Language: %v", s.language)
	}

	if strings.HasSuffix(s.config.modelFilename, "/") {
		return errors.New("Filenames can't end with \"/\"")
	}

	s.model = &SuffixTreeSet{}
	err = s.model.FromFileOrS3(s.config.modelFilename, nil)
	if err != nil {
		log.Fatalf("Failed to parse model: %v", err)
	}

	if verbose {
		log.Println("Read model into memory")
		// log.Printf("Model: %v", s.model)
	}

	return nil
}

func (s EFNLPService) GetValidText(
	ctx context.Context,
	req *efnlp.GetValidTextRequest,
) (*efnlp.GetValidTextResponse, error) {

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

	return &efnlp.IsValidTextResponse{
		Text:  req.Text,
		Valid: s.language.IsValidText(req.Text),
	}, nil

}

func (s EFNLPService) GetModelBlockSize(
	ctx context.Context,
	req *efnlp.GetModelBlockSizeRequest,
) (*efnlp.GetModelBlockSizeResponse, error) {

	// TODO: logging interceptor

	// TODO: request validation interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	return &efnlp.GetModelBlockSizeResponse{
		Size: s.model.GetDepth(),
	}, nil

}

func (s EFNLPService) GenerateBatch(
	ctx context.Context,
	req *efnlp.GenerateBatchRequest,
) (*efnlp.GenerateBatchResponse, error) {

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

	blockSize := s.model.GetDepth()

	stats := efnlp.Statistics{}
	for i = 0; i < req.Samples; i++ {
		start := time.Now()
		seq, err := s.model.Generate(req.BatchSize, blockSize, p) // []TokenType
		if err != nil {
			log.Printf("Error: %v", err)
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

	if req.Instrument {
		stats.GenFreqNs = float64(stats.GenTimeNs) / float64(req.BatchSize*req.Samples)
		resp.Stats = &stats
	}

	return &resp, nil
}

func (s EFNLPService) GenerateStream(
	req *efnlp.GenerateStreamRequest,
	stream efnlp.Generation_GenerateStreamServer,
) error {

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

	blockSize := s.model.GetDepth()

	for i := uint32(0); i < req.MaxBatches; i++ {

		stats := efnlp.Statistics{}
		start := time.Now()
		seq, err := s.model.Generate(req.BatchSize, blockSize, p) // []TokenType
		if err != nil {
			log.Printf("Error: %v", err)
			err := status.Error(
				codes.Internal,
				"There was an unexpected issue generating text",
			)
			return err
		}
		fp := MaxInt(len(p), int(blockSize))
		gen, err := s.language.Decode(seq[fp:]) // string
		if err != nil {

		}

		if req.Instrument {
			stats.GenTimeNs += time.Since(start).Nanoseconds()
			stats.GenFreqNs = float64(stats.GenTimeNs) / float64(req.BatchSize)
		}

		resp := efnlp.GenerateStreamResponse{Result: gen, Stats: &stats}
		if err := stream.Send(&resp); err != nil {
			log.Printf("send error %v", err)
		}

		p = seq[len(seq)-int(blockSize) : len(seq)]

	}

	return nil

}
