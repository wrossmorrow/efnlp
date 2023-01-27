package main

import (
	"flag"
	"log"
)

func main() {

	host := flag.String("host", "0.0.0.0", "gRPC host for clients (default: 0.0.0.0)")
	port := flag.Int("port", 50051, "gRPC port (default: 50051)")
	client := flag.Bool("client", false, "run the client (default: false, run the server)")
	language := flag.String("language", "", "language file (proto)")
	model := flag.String("model", "", "model file (proto)")
	quiet := flag.Bool("quiet", false, "don't print info to terminal")

	flag.Parse()
	verbose := !(*quiet)

	// args := flag.Args()
	// if len(args) == 0 {
	// 	log.Fatal("Passing a processor is required.")
	// } else if len(args) > 1 {
	// 	log.Fatal("Only a single processor can be served at once.")
	// } else {
	// 	_, exists := processors[args[0]]
	// 	if !exists {
	// 		log.Fatalf("Processor \"%s\" not defined.", args[0])
	// 	}
	// }

	if verbose {
		log.Printf("Settings: ")
		log.Printf("  host: %s", *host)
		log.Printf("  port: %d", *port)
		log.Printf("  client: %v", *client)
	}

	if *client {

		C := EFNLPClient{}
		log.Println("Running client")
		err := C.Connect(*host, *port)
		if err != nil {
			log.Fatalf("Failed to connect: %w", err)
		}
		defer C.Close()

		{
			log.Println("Attempting to get valid text")
			resp, err := C.GetValidText()
			if err != nil {
				log.Fatalf("Failed to get valid text: %w", err)
			}
			log.Printf("Successfully got valid text: %v", resp)
		}

		{
			log.Println("Attempting to validate text")

			resp, err := C.IsValidText("a")
			if err != nil {
				log.Fatalf("Failed to validate text: %v", err)
			}
			if resp.Valid {
				log.Printf("Successfully validated text: %v", resp)
			} else {
				log.Printf("Successfully invalidated text: %v", resp)
			}

			resp, err = C.IsValidText("!")
			if err != nil {
				log.Fatalf("Failed to validate text: %v", err)
			}
			if resp.Valid {
				log.Printf("Successfully validated text: %v", resp)
			} else {
				log.Printf("Successfully invalidated text: %v", resp)
			}

			resp, err = C.IsValidText("0")
			if err != nil {
				log.Fatalf("Failed to validate text: %v", err)
			}
			if resp.Valid {
				log.Printf("Successfully validated text: %v", resp)
			} else {
				log.Printf("Successfully invalidated text: %v", resp)
			}
		}

		{
			log.Println("Get model block size")
			resp, err := C.GetModelBlockSize()
			if err != nil {
				log.Fatalf("Failed to get model block size: %v", err)
			}
			log.Printf("Successfully got model block size: %v", resp)
		}

		{
			log.Println("Attempting to batch generate text")
			resp, err := C.GenerateBatch("\n", 1000, 10, true)
			if err != nil {
				log.Fatalf("Failed to batch generate text: %v", err)
			}
			log.Printf("Successfully batch generated text: %v", resp)
		}

		{
			log.Println("Attempting to stream generated text")
			err := C.GenerateStream("\n", 100, 10, true)
			if err != nil {
				log.Fatalf("Failed to stream generate text: %v", err)
			}
			log.Printf("Successfully streamed generated text")

		}

	} else {

		log.Println("Running server")
		conf := EFNLPServiceConfig{
			languageFilename: *language,
			modelFilename:    *model,
			verbose:          verbose,
		}
		service := EFNLPService{config: &conf}
		err := service.Initialize(verbose)
		if err != nil {
			log.Fatalf("Server initialization failed: %v", err)
		}
		Serve(*port, 100, service)

	}
}
