package main

import (
	"compress/gzip"
	"crypto/sha1"
	"encoding/hex"
	"io/ioutil"
	"log"
	"os"
	"strings"

	aws "github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-sdk-go/service/s3/s3manager"
)

func MaxInt(a int, b int) int {
	if a <= b {
		return b
	}
	return a
}

func MaxUInt32(a uint32, b uint32) uint32 {
	if a <= b {
		return b
	}
	return a
}

func hashUTF8(str []byte) string {
	// h := blake2b.Sum256(str) // longer strings; faster?
	h := sha1.Sum(str)
	return hex.EncodeToString(h[:])
}

type S3StyleUrl struct {
	Bucket   string
	Prefix   string
	Filename string
	Key      string
}

func DecodeS3Url(url string) (*S3StyleUrl, error) {

	// this is janky, but may be much faster than regexps
	// (albeit at the risk of being more buggy)

	// assert strings.StartsWith(url, "[sS]3://")?

	U := S3StyleUrl{}

	j := 5
	k := len(url) - 1

	for j < len(url) {
		if url[j] == '/' {
			break
		}
		j++
	}

	if url[k] == '/' {
		k--
	}
	for k > j {
		if url[k] == '/' {
			break
		}
		k--
	}

	U.Bucket = url[5:j]
	U.Filename = url[k+1:]
	if j < k {
		U.Prefix = url[j+1 : k]
		U.Key = U.Prefix + "/" + U.Filename
	} else {
		U.Key = U.Filename
	}

	return &U, nil

}

func DownloadS3File(
	s3url *S3StyleUrl,
	localFilename string,
	awsconf *aws.Config,
) (string, error) {

	var filename string
	if len(localFilename) > 0 {
		filename = localFilename
	} else {
		filename = s3url.Filename
	}

	file, err := os.Create(filename)
	if err != nil {
		return "", err
	}
	defer file.Close()

	// Initialize a session in us-west-2 that the SDK will use to load
	// credentials from the shared credentials file ~/.aws/credentials.
	var sess *session.Session
	if awsconf == nil {
		sess, _ = session.NewSession(&aws.Config{
			Region: aws.String("us-east-1"),
		})
	} else {
		sess, _ = session.NewSession(awsconf)
	}

	downloader := s3manager.NewDownloader(sess)
	_, err = downloader.Download(
		file,
		&s3.GetObjectInput{
			Bucket: aws.String(s3url.Bucket),
			Key:    aws.String(s3url.Key),
		},
	)
	if err != nil {
		return "", err
	}

	return filename, nil

}

func BytesFromFileOrS3(
	filename string,
	awsconf *aws.Config,
) ([]byte, error) {
	if strings.HasPrefix(filename, "s3://") {
		return BytesFromS3Obj(filename, awsconf)
	}
	return BytesFromLocalFile(filename)
}

func BytesFromS3Obj(
	filename string,
	awsconf *aws.Config,
) ([]byte, error) {
	U, err := DecodeS3Url(filename)
	if err != nil {
		return nil, err
	}
	log.Printf("Downloading \"%s\" from S3", filename)
	fn, err := DownloadS3File(U, "", awsconf)
	if err != nil {
		return nil, err
	}
	return BytesFromLocalFile(fn)
}

func BytesFromLocalFile(filename string) ([]byte, error) {
	if strings.HasSuffix(filename, ".gz") {
		log.Printf("Decompressing content in \"%s\"", filename)
		return BytesFromGzFile(filename)
	}
	in, err := ioutil.ReadFile(filename)
	if err != nil {
		return nil, err
	}
	return in, nil
}

func BytesFromGzFile(filename string) ([]byte, error) {

	gzfile, err := os.Open(filename)
	if err != nil {
		return nil, err
	}

	reader, err := gzip.NewReader(gzfile)
	if err != nil {
		return nil, err
	}
	defer reader.Close()

	content, err := ioutil.ReadAll(reader)
	if err != nil {
		return nil, err
	}

	return content, nil

}
