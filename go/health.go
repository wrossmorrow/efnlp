package main

import (
	"context"
	"log"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	hpb "google.golang.org/grpc/health/grpc_health_v1"
)

type HealthServer struct{}

func (s *HealthServer) Check(ctx context.Context, req *hpb.HealthCheckRequest) (*hpb.HealthCheckResponse, error) {
	log.Printf("Handling grpc Check request + %s", req.String())
	return &hpb.HealthCheckResponse{Status: hpb.HealthCheckResponse_SERVING}, nil
}

func (s *HealthServer) Watch(req *hpb.HealthCheckRequest, srv hpb.Health_WatchServer) error {
	return status.Error(codes.Unimplemented, "Watch is not implemented")
}
