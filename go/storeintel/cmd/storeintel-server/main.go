package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	storeintel "github.com/catch-radar/storeintel"
	"github.com/catch-radar/storeintel/gateway"
	"github.com/catch-radar/storeintel/jobs"
	"github.com/catch-radar/storeintel/repo"
	"github.com/catch-radar/storeintel/schema"
	"github.com/catch-radar/storeintel/service"

	_ "github.com/go-sql-driver/mysql"
)

func main() {
	if err := run(); err != nil {
		log.Fatal(err)
	}
}

func run() error {
	addr := flag.String("addr", envString("STOREINTEL_ADDR", "127.0.0.1:18080"), "HTTP listen address")
	dsn := flag.String("dsn", os.Getenv("STOREINTEL_MYSQL_DSN"), "MySQL DSN")
	useMemory := flag.Bool("memory", envBool("STOREINTEL_MEMORY", false), "use in-memory repository")
	skipMigrate := flag.Bool("skip-migrate", envBool("STOREINTEL_SKIP_MIGRATE", false), "skip MySQL schema migration")
	runScheduler := flag.Bool("scheduler", envBool("STOREINTEL_RUN_SCHEDULER", true), "run background scheduler")
	queueBackend := flag.String("queue-backend", envString("STOREINTEL_QUEUE_BACKEND", "local"), "refresh job queue backend: local or redis")
	redisURL := flag.String("redis-url", envStringAllowEmpty("STOREINTEL_REDIS_URL", envStringAllowEmpty("CATCH_RADAR_REDIS_URL", "")), "Redis URL for refresh job queue")
	redisStream := flag.String("redis-stream", envString("STOREINTEL_REDIS_STREAM", "storeintel:refresh_jobs"), "Redis stream for refresh jobs")
	redisGroup := flag.String("redis-group", envString("STOREINTEL_REDIS_GROUP", "storeintel-refresh-workers"), "Redis consumer group for refresh jobs")
	corpusURL := flag.String("corpus-url", envStringAllowEmpty("CATCH_RADAR_CORPUS_URL", service.DefaultKeywordCorpusURL), "shared keyword corpus Worker URL; empty disables remote corpus")
	corpusKey := flag.String("corpus-key", envStringAllowEmpty("CATCH_RADAR_CORPUS_KEY", service.DefaultKeywordCorpusKey), "shared keyword corpus API key")
	smokeTest := flag.Bool("smoke-test", false, "initialize dependencies and exit")
	flag.Parse()

	storeRepo, cleanup, err := buildRepo(*dsn, *useMemory, *skipMigrate)
	if err != nil {
		return err
	}
	defer cleanup()

	var corpusClient service.KeywordCorpusClient
	if *corpusURL != "" {
		corpusClient = service.NewHTTPKeywordCorpusClient(service.HTTPKeywordCorpusClientConfig{
			BaseURL: *corpusURL,
			APIKey:  *corpusKey,
		})
	}
	module, err := storeintel.NewModule(storeintel.Dependencies{
		Repo:          storeRepo,
		KeywordCorpus: corpusClient,
	})
	if err != nil {
		return err
	}
	queue, cleanupQueue, err := buildRefreshJobQueue(*queueBackend, *redisURL, *redisStream, *redisGroup)
	if err != nil {
		return err
	}
	defer cleanupQueue()
	handlerOpts := []gateway.HandlerOption{}
	if queue != nil {
		handlerOpts = append(handlerOpts, gateway.WithRefreshJobQueue(queue))
	}
	handler := gateway.NewHandler(module.Service, handlerOpts...)
	if err := module.Service.EnsureSettingsDefaults(context.Background()); err != nil {
		return err
	}
	if *smokeTest {
		fmt.Println("storeintel-server-ok")
		return nil
	}
	schedulerCtx, cancelScheduler := context.WithCancel(context.Background())
	defer cancelScheduler()
	if *runScheduler {
		scheduler := jobs.NewScheduler(module.Service)
		scheduler.Start(schedulerCtx)
		defer scheduler.Stop()
		log.Print("storeintel scheduler enabled")
	}

	server := &http.Server{
		Addr:              *addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("storeintel server listening on http://%s", *addr)
	return server.ListenAndServe()
}

func buildRepo(dsn string, useMemory bool, skipMigrate bool) (repo.StoreIntelRepo, func(), error) {
	if useMemory {
		return repo.NewMemoryRepo(), func() {}, nil
	}
	if dsn == "" {
		return nil, func() {}, fmt.Errorf("STOREINTEL_MYSQL_DSN or -dsn is required unless -memory is set")
	}
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, func() {}, err
	}
	cleanup := func() { _ = db.Close() }
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		cleanup()
		return nil, func() {}, err
	}
	if !skipMigrate {
		if err := schema.ApplyMySQL(ctx, db); err != nil {
			cleanup()
			return nil, func() {}, err
		}
	}
	return repo.NewSQLRepo(db), cleanup, nil
}

func buildRefreshJobQueue(backend, redisURL, redisStream, redisGroup string) (gateway.RefreshJobQueue, func(), error) {
	switch strings.ToLower(strings.TrimSpace(backend)) {
	case "", "local", "memory", "mysql":
		return nil, func() {}, nil
	case "redis":
		queue, cleanup, err := gateway.NewRedisRefreshJobQueue(gateway.RedisRefreshJobQueueConfig{
			URL:    redisURL,
			Stream: redisStream,
			Group:  redisGroup,
		})
		if err != nil {
			return nil, func() {}, err
		}
		return queue, func() { _ = cleanup() }, nil
	default:
		return nil, func() {}, fmt.Errorf("unsupported STOREINTEL_QUEUE_BACKEND %q", backend)
	}
}

func envString(key string, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envStringAllowEmpty(key string, fallback string) string {
	value, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}
	return value
}

func envBool(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	switch value {
	case "1", "t", "T", "true", "TRUE", "True", "yes", "YES", "on", "ON":
		return true
	case "0", "f", "F", "false", "FALSE", "False", "no", "NO", "off", "OFF":
		return false
	default:
		return fallback
	}
}
