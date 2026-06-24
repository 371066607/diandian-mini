package gateway

import (
	"testing"

	"github.com/redis/go-redis/v9"
)

func TestRedisRefreshJobRecordDecodesRequestJSON(t *testing.T) {
	record, err := redisRefreshJobRecord(redis.XMessage{
		ID: "1-0",
		Values: map[string]any{
			"job_id":       "job-1",
			"kind":         "search",
			"request_json": `{"kind":"search","query":"demo","country":"us","lang":"en","limit":5}`,
		},
	})
	if err != nil {
		t.Fatalf("decode redis refresh job: %v", err)
	}
	if record.Job.JobID != "job-1" || record.Job.Kind != "search" {
		t.Fatalf("unexpected job: %+v", record.Job)
	}
	if record.Request.Kind != "search" || record.Request.Query != "demo" ||
		record.Request.Country != "us" || record.Request.Limit != 5 {
		t.Fatalf("unexpected request: %+v", record.Request)
	}
}

func TestRedisRefreshJobRecordRejectsMissingJobID(t *testing.T) {
	if _, err := redisRefreshJobRecord(redis.XMessage{Values: map[string]any{}}); err == nil {
		t.Fatal("missing job_id should fail")
	}
}
