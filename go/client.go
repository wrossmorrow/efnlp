package main

import (
	"context"
	"fmt"
	"io"
	"log"

	grpc "google.golang.org/grpc"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"

	efnlp "github.com/wrossmorrow/efnlp/gen"
)

type EFNLPClient struct {
	addr string
	conn *grpc.ClientConn
	svc  efnlp.GenerationClient
}

// for channel-based streaming
type ClientStreamMessage struct {
	Message *efnlp.GenerateStreamResponse
	Error   error
	Done    bool
}

func (c *EFNLPClient) Connect(host string, port int) error {
	c.addr = fmt.Sprintf("%s:%d", host, port)
	log.Printf("Connecting to %s", c.addr)
	conn, err := grpc.Dial(c.addr, grpc.WithBlock(), grpc.WithInsecure())
	if err != nil {
		return fmt.Errorf("Failed to connect to GenerationService on %s: %w", c.addr, err)
	}
	c.conn = conn
	c.svc = efnlp.NewGenerationClient(c.conn)
	return nil
}

func (c *EFNLPClient) Close() error {
	return c.conn.Close()
}

func (c *EFNLPClient) GetValidText() (*efnlp.GetValidTextResponse, error) {

	if c.svc == nil {
		c.svc = efnlp.NewGenerationClient(c.conn)
	}

	req := efnlp.GetValidTextRequest{}

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	resp, err := (c.svc).GetValidText(context.Background(), &req)
	if err != nil { // TODO: interceptor
		st, ok := status.FromError(err)
		log.Printf("Error %v, %v", st, ok)
		if !ok { // Error was not a status error
			log.Printf("Error %v", err)
			return nil, err
		}
		log.Printf("(%v) %v", st.Code(), st.Message())
		return nil, err // TODO: how to send back status object?
	}
	return resp, nil
}

func (c *EFNLPClient) IsValidText(
	text string,
) (*efnlp.IsValidTextResponse, error) {

	if c.svc == nil {
		c.svc = efnlp.NewGenerationClient(c.conn)
	}

	req := efnlp.IsValidTextRequest{Text: text}

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	resp, err := (c.svc).IsValidText(context.Background(), &req)
	if err != nil { // TODO: interceptor
		st, ok := status.FromError(err)
		log.Printf("Error %v, %v", st, ok)
		if !ok { // Error was not a status error
			log.Printf("Error %v", err)
			return nil, err
		}
		log.Printf("(%v) %v", st.Code(), st.Message())
		return nil, err // TODO: how to send back status object?
	}
	return resp, nil

}

func (c *EFNLPClient) GetModelBlockSize() (*efnlp.GetModelBlockSizeResponse, error) {

	if c.svc == nil {
		c.svc = efnlp.NewGenerationClient(c.conn)
	}

	req := efnlp.GetModelBlockSizeRequest{}

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	resp, err := (c.svc).GetModelBlockSize(context.Background(), &req)
	if err != nil { // TODO: interceptor
		st, ok := status.FromError(err)
		log.Printf("Error %v, %v", st, ok)
		if !ok { // Error was not a status error
			log.Printf("Error %v", err)
			return nil, err
		}
		log.Printf("(%v) %v", st.Code(), st.Message())
		return nil, err // TODO: how to send back status object?
	}
	return resp, nil
}

func (c *EFNLPClient) GenerateBatch(
	prompt string,
	tokens uint32,
	samples uint32,
	instrument bool,
) (*efnlp.GenerateBatchResponse, error) {

	if c.svc == nil {
		c.svc = efnlp.NewGenerationClient(c.conn)
	}

	req := efnlp.GenerateBatchRequest{
		Prompt:     &efnlp.Prompt{Value: &efnlp.Prompt_Text{Text: prompt}},
		BatchSize:  tokens,
		Samples:    samples,
		Instrument: instrument,
	}

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		status.Error(codes.InvalidArgument, msg)
	}

	resp, err := (c.svc).GenerateBatch(context.Background(), &req)
	if err != nil { // TODO: interceptor
		st, ok := status.FromError(err)
		log.Printf("Error %v, %v", st, ok)
		if !ok { // Error was not a status error
			log.Printf("Error %v", err)
			return nil, err
		}
		log.Printf("(%v) %v", st.Code(), st.Message())
		return nil, err // TODO: how to send back status object?
	}
	return resp, nil

}

func (c *EFNLPClient) GenerateStream(
	prompt string,
	batchSize uint32,
	batches uint32,
	instrument bool,
) (<-chan ClientStreamMessage, error) {
	// (*efnlp.GenerateStreamResponse, error) {

	if c.svc == nil {
		c.svc = efnlp.NewGenerationClient(c.conn)
	}

	req := efnlp.GenerateStreamRequest{
		Prompt:     &efnlp.Prompt{Value: &efnlp.Prompt_Text{Text: prompt}},
		BatchSize:  batchSize,
		MaxBatches: batches,
		Instrument: instrument,
	}

	// TODO: interceptor
	err := req.Validate()
	if err != nil {
		msg := fmt.Sprintf("InvalidRequest: %v", err)
		return nil, status.Error(codes.InvalidArgument, msg)
	}

	stream, err := (c.svc).GenerateStream(context.Background(), &req)
	if err != nil {
		log.Fatalf("open stream error %v", err)
		return nil, err
	}

	msgs := make(chan ClientStreamMessage)
	go func() {
		defer close(msgs)
		for {
			msg := ClientStreamMessage{Done: false}
			resp, err := stream.Recv()
			if err == io.EOF {
				msg.Done = true
				msgs <- msg // stream is finished
				return
			}
			if err != nil {
				msg.Error = err
				msgs <- msg
				return
			}
			msg.Message = resp
			msgs <- msg
		}
	}()

	return msgs, nil

}
