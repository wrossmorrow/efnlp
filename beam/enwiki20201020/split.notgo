package main

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"strings"

	"github.com/apache/beam/sdks/v2/go/pkg/beam"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/io/bigqueryio"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/io/textio"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/register"
	"github.com/apache/beam/sdks/v2/go/pkg/beam/x/beamx"

	"cloud.google.com/go/storage"
	"google.golang.org/api/iterator"
)

var (
	bucket = flag.String("bucket", "", "Bucket to search")
	prefix = flag.String("prefix", "", "Prefix to search")

	// Set this required option to specify where to write the output.
	//
	//		gs://... for cloud storage
	//		bq://<project_id>:<dataset>.<table> for bigquery
	//
	output = flag.String("output", "", "Output file (required).")
)

type WikiArticleJSON struct {
	Src   string `bigquery:"src"`
	Id    string `json:"id" bigquery:"id"`
	Title string `json:"title" bigquery:"title"`
	Text  string `json:"text" bigquery:"text"`
}

type GCSObjSpec struct {
	Bucket string
	Key    string
}

func ListMatchingFilesInGCSBucket(
	bucket string,
	prefix string,
) ([]GCSObjSpec, error) {

	var names []GCSObjSpec

	ctx := context.Background()
	client, err := storage.NewClient(ctx)
	if err != nil {
		return nil, err
	}
	B := client.Bucket(bucket)

	qry := &storage.Query{Prefix: prefix}
	iter := B.Objects(ctx, qry)
	for {
		attrs, err := iter.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, err
		}
		names = append(names, GCSObjSpec{
			Bucket: bucket,
			Key:    attrs.Name,
		})
	}

	return names, nil

}

func AnnoyinglyReadOnlyOneGCSFile(
	ctx context.Context,
	spec GCSObjSpec,
) ([]WikiArticleJSON, error) {

	var articles []WikiArticleJSON
	var decoder *json.Decoder

	client, err := storage.NewClient(ctx)
	if err != nil {
		return nil, err
	}
	B := client.Bucket(spec.Bucket)

	obj := B.Object(spec.Key).ReadCompressed(true)
	r, err := obj.NewReader(ctx)
	if err != nil {
		return nil, err
	}
	defer r.Close()

	if strings.HasSuffix(spec.Key, ".gz") {
		gz, err := gzip.NewReader(r)
		if err != nil {
			return nil, err
		}
		defer gz.Close() // IS THIS CORRECT????
		decoder = json.NewDecoder(gz)
	} else {
		decoder = json.NewDecoder(r)
	}

	decoder.UseNumber()
	err = decoder.Decode(&articles)
	if err != nil {
		return nil, err
	}

	for i := 0; i < len(articles); i++ {
		articles[i].Src = spec.Bucket + "/" + spec.Key
	}

	return articles, nil

}

type AnnoyingJSONFileTransformer struct{}

func (f *AnnoyingJSONFileTransformer) ProcessElement(
	ctx context.Context,
	spec GCSObjSpec,
	emit func(WikiArticleJSON),
) {
	articles, err := AnnoyinglyReadOnlyOneGCSFile(ctx, spec)
	if err != nil {
		panic(fmt.Sprintf("Failure to read file: %v", err))
	}
	for _, article := range articles {
		emit(article)
	}
}

func JSONLineFormat(a WikiArticleJSON) string {
	b, err := json.Marshal(a)
	if err != nil {
		panic(fmt.Sprintf("Failure to marshal json: %v | %v", a, err))
	}
	return string(b)
}

// registrations
func init() {
	register.DoFn3x0[
		context.Context,
		GCSObjSpec,
		func(WikiArticleJSON),
	](&AnnoyingJSONFileTransformer{})
	register.Function1x1(JSONLineFormat)
	register.Emitter1[WikiArticleJSON]() // WTF?
}

func main() {

	// If beamx or Go flags are used, flags must be parsed first.
	flag.Parse()

	prjFlag := flag.Lookup("project")
	if prjFlag == nil {
		log.Fatal("--project not provided")
	}
	project := prjFlag.Value.String()

	beam.Init()

	if *bucket == "" {
		log.Fatal("No output provided")
	}
	if *output == "" {
		log.Fatal("No output provided")
	}

	// we will need to process files "in bulk" in their array-json form
	// that is, we should parallelize over _filenames_, read in each file
	// in parallel, parse the json, and emit structs to write to bigquery

	specs, err := ListMatchingFilesInGCSBucket(*bucket, *prefix)
	if err != nil {
		log.Fatalf("Error: %v", err)
	}
	log.Printf("Found %d objects (won't print 'em')", len(specs))

	p := beam.NewPipeline()
	s := p.Root()

	filesPC := beam.CreateList(s, specs)
	disaggd := beam.ParDo(s, &AnnoyingJSONFileTransformer{}, filesPC)
	if strings.HasPrefix(*output, "gs://") {
		formatted := beam.ParDo(s, JSONLineFormat, disaggd)
		textio.Write(s, *output, formatted)
	} else if strings.HasPrefix(*output, "bq://") {
		bigqueryio.Write(s, project, (*output)[5:], disaggd)
	} else {
		formatted := beam.ParDo(s, JSONLineFormat, disaggd)
		textio.Write(s, *output, formatted)
	}

	if err := beamx.Run(context.Background(), p); err != nil {
		log.Fatalf("Failed to execute job: %v", err)
	}
}
