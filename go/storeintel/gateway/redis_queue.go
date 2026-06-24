package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/catch-radar/storeintel/dto"
	"github.com/redis/go-redis/v9"
)

const (
	defaultRedisRefreshJobStream = "storeintel:refresh_jobs"
	defaultRedisRefreshJobGroup  = "storeintel-refresh-workers"
)

type RedisRefreshJobQueueConfig struct {
	URL    string
	Stream string
	Group  string
}

type redisRefreshJobQueue struct {
	client *redis.Client
	stream string
	group  string
}

func NewRedisRefreshJobQueue(cfg RedisRefreshJobQueueConfig) (RefreshJobQueue, func() error, error) {
	url := strings.TrimSpace(cfg.URL)
	if url == "" {
		return nil, func() error { return nil }, fmt.Errorf("redis url is required")
	}
	options, err := redis.ParseURL(url)
	if err != nil {
		return nil, func() error { return nil }, err
	}
	client := redis.NewClient(options)
	queue := &redisRefreshJobQueue{
		client: client,
		stream: coalesceString(cfg.Stream, defaultRedisRefreshJobStream),
		group:  coalesceString(cfg.Group, defaultRedisRefreshJobGroup),
	}
	return queue, client.Close, nil
}

func (q *redisRefreshJobQueue) Enqueue(ctx context.Context, record dto.RefreshJobRecord) error {
	if q == nil || q.client == nil {
		return errors.New("redis refresh queue is not configured")
	}
	requestJSON, err := json.Marshal(record.Request)
	if err != nil {
		return err
	}
	return q.client.XAdd(ctx, &redis.XAddArgs{
		Stream: q.stream,
		Values: map[string]any{
			"job_id":       record.Job.JobID,
			"kind":         record.Job.Kind,
			"request_json": string(requestJSON),
		},
	}).Err()
}

func (q *redisRefreshJobQueue) Start(ctx context.Context, workerID string, handle func(context.Context, dto.RefreshJobRecord) error) {
	if q == nil || q.client == nil || handle == nil {
		return
	}
	workerID = coalesceString(workerID, refreshWorkerID())
	for {
		if err := q.ensureGroup(ctx); err != nil {
			if !sleepOrDone(ctx, time.Second) {
				return
			}
			continue
		}
		break
	}
	for {
		streams, err := q.client.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    q.group,
			Consumer: workerID,
			Streams:  []string{q.stream, ">"},
			Count:    10,
			Block:    time.Second,
		}).Result()
		if err != nil {
			if errors.Is(err, redis.Nil) {
				continue
			}
			if !sleepOrDone(ctx, time.Second) {
				return
			}
			continue
		}
		for _, stream := range streams {
			for _, message := range stream.Messages {
				record, decodeErr := redisRefreshJobRecord(message)
				if decodeErr == nil {
					_ = handle(ctx, record)
				}
				_ = q.client.XAck(ctx, q.stream, q.group, message.ID).Err()
			}
		}
	}
}

func (q *redisRefreshJobQueue) ensureGroup(ctx context.Context) error {
	err := q.client.XGroupCreateMkStream(ctx, q.stream, q.group, "0").Err()
	if err != nil && strings.Contains(err.Error(), "BUSYGROUP") {
		return nil
	}
	return err
}

func redisRefreshJobRecord(message redis.XMessage) (dto.RefreshJobRecord, error) {
	jobID := strings.TrimSpace(fmt.Sprint(message.Values["job_id"]))
	if jobID == "" {
		return dto.RefreshJobRecord{}, fmt.Errorf("redis refresh job missing job_id")
	}
	kind := strings.TrimSpace(fmt.Sprint(message.Values["kind"]))
	requestJSON := strings.TrimSpace(fmt.Sprint(message.Values["request_json"]))
	var req dto.RefreshJobRequest
	if requestJSON != "" {
		if err := json.Unmarshal([]byte(requestJSON), &req); err != nil {
			return dto.RefreshJobRecord{}, err
		}
	}
	if req.Kind == "" {
		req.Kind = kind
	}
	return dto.RefreshJobRecord{
		Job: dto.RefreshJobResponse{
			JobID: jobID,
			Kind:  kind,
		},
		Request: req,
	}, nil
}

func coalesceString(values ...string) string {
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			return value
		}
	}
	return ""
}

func sleepOrDone(ctx context.Context, delay time.Duration) bool {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
