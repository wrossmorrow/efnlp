package main

import (
	"flag"
	"log"
	"strings"
	"time"
)

func main() {

	host := flag.String("host", "0.0.0.0", "gRPC host for clients (default: 0.0.0.0)")
	port := flag.Int("port", 50051, "gRPC port (default: 50051)")
	client := flag.Bool("client", false, "run the client (default: false, run the server)")
	language := flag.String("language", "", "language file (proto)")
	model := flag.String("model", "", "model file (proto)")
	quiet := flag.Bool("quiet", false, "don't print info to terminal")

	_parse := flag.Bool("parse", false, "parse data, requires `input` flag set")
	input := flag.String("input", "", "input (text) file to actually parse")
	block := flag.Int("block", 10, "token sequence block size (or window) to parse")
	generate := flag.Int("generate", 10, "number of tokens to generate")
	printgen := flag.Bool("print", true, "print generated text")
	// we can interpret language/model flags as output?

	flag.Parse()
	verbose := !(*quiet)
	server := !(*client)
	parse := *_parse // deref for convenience

	// args := flag.Args()
	// if len(args) == 0 {
	//  log.Fatal("Passing a processor is required.")
	// } else if len(args) > 1 {
	//  log.Fatal("Only a single processor can be served at once.")
	// } else {
	//  _, exists := processors[args[0]]
	//  if !exists {
	//      log.Fatalf("Processor \"%s\" not defined.", args[0])
	//  }
	// }

	if parse {
		ParseInput(*input, *language, *block, *model, *generate, *printgen, verbose)
	} else if server {
		RunServer(*port, *language, *model, verbose)
	} else {
		RunClient(*host, *port, verbose)
	}

}

func ParseInput(
	in string,
	language string,
	block int,
	model string,
	generate int,
	printgen bool,
	verbose bool,
) {

	if verbose {
		log.Printf("Parse Settings: ")
		log.Printf("  input: %s", in)
		log.Printf("  language: %s", language)
		log.Printf("  model: %s", model)
	}

	if len(in) == 0 {
		log.Fatalf("Config Error: input is required (via -input=[s3://]path/to/input.txt)")
	}
	if len(language) == 0 {
		log.Fatalf("Config Error: Language spec is required (via -language=[s3://]path/to/lang.proto[.gz])")
	}

	// need to parse or read language
	// probably read language is more appropriate...

	lang := Language{}
	err := lang.FromFileOrS3(language, nil) // (no special AWS config)
	if err != nil {
		log.Fatalf("Failed to parse language: %v", err)
	}
	if verbose {
		log.Println("Read language into memory")
	}

	data, err := BytesFromFileOrS3(in, nil)
	if err != nil {
		log.Fatalf("Failed to read input: %v", err)
	}
	if verbose {
		log.Println("Read input in memory")
	}

	tokenized, err := lang.Encode(string(data), false) // TODO: cast ok? copies?
	if err != nil {
		log.Fatalf("Failed to tokenize input: %v", err)
	}
	if verbose {
		log.Println("Tokenized input in memory")
	}
	// TODO: delete `data` from memory! If we've encoded, we
	// don't require the string bytes anymore...

	start := time.Now()
	parser := EFNLPParser{Lang: &lang}
	parser.Parse(tokenized, block, verbose)
	duration_ns := time.Since(start).Milliseconds()
	if verbose {
		log.Printf("Parsed model from tokenized input in %dms", duration_ns)
	}

	if len(model) > 0 {
		parser.Dump(model, strings.HasSuffix(model, ".gz"))
		if verbose {
			log.Printf("Dumped model (proto) to file %s", model)
		}
	}

	if generate > 0 {

		G := generate
		B := block

		start = time.Now()
		prompt := []TokenType{0}
		gen, err := parser.Trees.Generate(G, B, prompt)
		duration_us := time.Since(start).Microseconds()
		if err != nil {
			log.Fatalf("Failed to generate text: %v", err)
		}
		log.Printf("Generated %d tokens at %f us/tok", G, float64(duration_us)/float64(G))

		if printgen {
			str, err := lang.Decode(gen)
			if err != nil {
				log.Fatalf("Failed to decode generated text: %v", err)
			}
			log.Printf("Generated: %s", str)
		}

	}

}

func RunServer(port int, language string, model string, verbose bool) {

	if verbose {
		log.Printf("Server Settings: ")
		log.Printf("  port: %d", port)
		log.Printf("  language: %s", language)
		log.Printf("  model: %s", model)
	}

	if len(language) == 0 {
		log.Fatalf("Config Error: Language spec is required (via -language=[s3://]path/to/lang.proto[.gz])")
	}
	if len(model) == 0 {
		log.Fatalf("Config Error: Model spec is required (via -model=[s3://]path/to/model.proto[.gz])")
	}

	log.Println("Initializing server")
	conf := EFNLPServiceConfig{
		languageFilename: language,
		modelFilename:    model,
		verbose:          verbose,
	}

	service := EFNLPService{config: &conf}
	err := service.Initialize(verbose)
	if err != nil {
		log.Fatalf("Server initialization failed: %v", err)
	}

	log.Println("Starting server")
	Serve(port, 100, service)

}

func RunClient(host string, port int, verbose bool) {

	if verbose {
		log.Printf("Client Settings: ")
		log.Printf("  host: %s", host)
		log.Printf("  port: %d", port)
	}

	C := EFNLPClient{}
	log.Println("Running client")
	err := C.Connect(host, port)
	if err != nil {
		log.Fatalf("Failed to connect: %v", err)
	}
	defer C.Close()

	{
		log.Println("Attempting to get valid text")
		resp, err := C.GetValidText()
		if err != nil {
			log.Fatalf("Failed to get valid text: %v", err)
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

	{ // "test case" passed, this fails with service validation interceptor
		log.Println("Attempting to fail to batch generate text")
		_, err := C.GenerateBatch("\n", 1000, 1000000, true)
		if err == nil {
			log.Fatalf("Failed to fail to batch generated text")
		}
		log.Printf("Successfully failed to batch generate text: %v", err)
	}

	{
		log.Println("Attempting to stream generated text")
		msgs, err := C.GenerateStream("\n", 100, 10, true)

		if err != nil {
			log.Fatalf("Failed to stream generate text: %v", err)
		}
		log.Printf("Successfully initiated streaming generated text")

		for {
			msg := <-msgs
			if msg.Done {
				log.Printf("Stream appears complete")
				break
			}
			if msg.Error != nil {
				log.Printf("Streaming error: %v", msg.Error)
				break
			}
			log.Printf("Text received: %v", msg.Message)
		}

	}

	{
		log.Println("Attempting to fail to stream generated text")
		_, err := C.GenerateStream("\n", 100, 10000000, true)

		if err == nil {
			log.Fatalf("Failed to invalidate request to stream generated text")
		}
		log.Printf("Successfully failed to stream generated text: %v", err)

	}

}
