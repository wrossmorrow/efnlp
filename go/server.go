package main

import (
	"log"
	"net"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	intc "github.com/grpc-ecosystem/go-grpc-middleware"
	recovery "github.com/grpc-ecosystem/go-grpc-middleware/recovery"
	validator "github.com/grpc-ecosystem/go-grpc-middleware/validator"
	grpc "google.golang.org/grpc"

	hpb "google.golang.org/grpc/health/grpc_health_v1"

	efnlp "github.com/wrossmorrow/efnlp/gen"
)

func Serve(port int, streams uint32, service efnlp.GenerationServer) {

	lis, err := net.Listen("tcp", ":"+strconv.Itoa(port))
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	sopts := []grpc.ServerOption{
		grpc.MaxConcurrentStreams(streams),
		grpc.UnaryInterceptor(
			intc.ChainUnaryServer(
				validator.UnaryServerInterceptor(), // TODO: not working
				recovery.UnaryServerInterceptor(),  // TODO: working?
			),
		),
		grpc.StreamInterceptor(
			intc.ChainStreamServer(
				validator.StreamServerInterceptor(), // TODO: not working
				recovery.StreamServerInterceptor(),  // TODO: working?
			),
		),
	}
	server := grpc.NewServer(sopts...)

	hpb.RegisterHealthServer(server, &HealthServer{})
	efnlp.RegisterGenerationServer(server, service)

	log.Printf("Starting gRPC listening on port %d\n", port)

	var gracefulStop = make(chan os.Signal)
	signal.Notify(gracefulStop, syscall.SIGTERM)
	signal.Notify(gracefulStop, syscall.SIGINT)
	go func() {
		sig := <-gracefulStop
		log.Printf("caught sig: %+v", sig)
		log.Println("Wait for 1 second to finish processing")
		time.Sleep(1 * time.Second)
		os.Exit(0)
	}()
	server.Serve(lis)

}
