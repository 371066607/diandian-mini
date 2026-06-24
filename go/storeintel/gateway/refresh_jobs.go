package gateway

import (
	"context"
	"fmt"
	"strings"
	"sync/atomic"
	"time"

	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/service"
)

type refreshJobManager struct {
	service service.StoreIntelService
	seq     uint64
	worker  string
	queue   RefreshJobQueue
}

type RefreshJobQueue interface {
	Enqueue(ctx context.Context, record dto.RefreshJobRecord) error
	Start(ctx context.Context, workerID string, handle func(context.Context, dto.RefreshJobRecord) error)
}

const (
	refreshJobRecoveryLimit = 100
	refreshJobLockTTL       = 24 * time.Hour
)

func newRefreshJobManager(storeService service.StoreIntelService, queue RefreshJobQueue) *refreshJobManager {
	manager := &refreshJobManager{
		service: storeService,
		worker:  refreshWorkerID(),
		queue:   queue,
	}
	if manager.queue != nil {
		go manager.queue.Start(context.Background(), manager.worker, manager.consumeRecord)
	}
	go manager.recoverUnfinished()
	return manager
}

func (m *refreshJobManager) Enqueue(ctx context.Context, req dto.RefreshJobRequest) (dto.RefreshJobResponse, error) {
	if m == nil || m.service == nil {
		return dto.RefreshJobResponse{}, service.ErrServiceUnavailable
	}
	req.Kind = strings.ToLower(strings.TrimSpace(req.Kind))
	if req.Kind == "" {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh kind is required", service.ErrInvalidRequest)
	}
	now := refreshJobNow()
	job := dto.RefreshJobResponse{
		JobID:       refreshJobID(atomic.AddUint64(&m.seq, 1)),
		Kind:        req.Kind,
		Status:      "queued",
		Message:     "刷新请求已加入服务器队列。",
		RequestedAt: now,
		UpdatedAt:   now,
	}
	job, err := m.service.CreateRefreshJob(ctx, req, job)
	if err != nil {
		return dto.RefreshJobResponse{}, err
	}

	if !m.dispatch(dto.RefreshJobRecord{Job: job, Request: req}) {
		go m.run(job.JobID, req)
	}
	return job, nil
}

func (m *refreshJobManager) Get(ctx context.Context, jobID string) (dto.RefreshJobResponse, error) {
	if m == nil || m.service == nil {
		return dto.RefreshJobResponse{}, service.ErrServiceUnavailable
	}
	return m.service.GetRefreshJob(ctx, jobID)
}

func (m *refreshJobManager) recoverUnfinished() {
	if m == nil || m.service == nil {
		return
	}
	records, err := m.service.ListRefreshJobs(
		context.Background(),
		[]string{"queued", "running"},
		refreshJobRecoveryLimit,
	)
	if err != nil {
		return
	}
	for _, record := range records {
		req := record.Request
		if strings.TrimSpace(req.Kind) == "" {
			req.Kind = record.Job.Kind
		}
		record.Request = req
		if !m.dispatch(record) {
			go m.run(record.Job.JobID, req)
		}
	}
}

func (m *refreshJobManager) dispatch(record dto.RefreshJobRecord) bool {
	if m == nil || m.queue == nil {
		return false
	}
	return m.queue.Enqueue(context.Background(), record) == nil
}

func (m *refreshJobManager) consumeRecord(_ context.Context, record dto.RefreshJobRecord) error {
	req := record.Request
	if strings.TrimSpace(req.Kind) == "" {
		req.Kind = record.Job.Kind
	}
	m.run(record.Job.JobID, req)
	return nil
}

func (m *refreshJobManager) run(jobID string, req dto.RefreshJobRequest) {
	job, claimed, err := m.service.ClaimRefreshJob(context.Background(), jobID, m.worker, refreshJobLockTTL)
	if err != nil || !claimed {
		return
	}
	startedAt := job.StartedAt
	if strings.TrimSpace(startedAt) == "" {
		startedAt = refreshJobNow()
	}
	err = m.runJob(context.Background(), req)
	status := "completed"
	message := "服务器后台刷新完成。"
	if err != nil {
		status = "failed"
		message = err.Error()
	}
	_, _ = m.service.UpdateRefreshJob(context.Background(), dto.RefreshJobResponse{
		JobID:      jobID,
		Kind:       req.Kind,
		Status:     status,
		Message:    message,
		StartedAt:  startedAt,
		FinishedAt: refreshJobNow(),
	})
}

func (m *refreshJobManager) runJob(ctx context.Context, req dto.RefreshJobRequest) error {
	switch req.Kind {
	case "all", "sync_all":
		_, err := m.service.SyncAll(ctx, dto.SyncAllRequest{DueOnly: req.DueOnly})
		return err
	case "due", "sync_due":
		_, err := m.service.SyncAll(ctx, dto.SyncAllRequest{DueOnly: true})
		return err
	case "search":
		result, err := m.service.SearchApps(ctx, dto.SearchAppsRequest{
			Query:   req.Query,
			Country: req.Country,
			Lang:    req.Lang,
			Limit:   req.Limit,
		})
		if err != nil {
			return err
		}
		var firstErr error
		synced := 0
		for _, item := range result.Items {
			appID := strings.TrimSpace(item.AppID)
			if appID == "" {
				continue
			}
			_, err := m.service.SyncAppNow(ctx, dto.SyncAppNowRequest{
				AppID:   appID,
				Country: req.Country,
				Lang:    req.Lang,
			})
			if err != nil {
				if firstErr == nil {
					firstErr = err
				}
				continue
			}
			synced++
		}
		if len(result.Items) > 0 && synced == 0 && firstErr != nil {
			return firstErr
		}
		return nil
	case "app":
		_, err := m.service.SyncAppNow(ctx, dto.SyncAppNowRequest{
			AppID:   req.AppID,
			Country: req.Country,
			Lang:    req.Lang,
		})
		return err
	case "keyword":
		_, err := m.service.SyncTrackedKeywordNow(ctx, dto.SyncTrackedKeywordRequest{
			Keyword: req.Keyword,
			AppID:   req.AppID,
			Country: req.Country,
			Lang:    req.Lang,
			Limit:   req.Limit,
		})
		return err
	case "chart":
		if strings.TrimSpace(req.AppID) != "" {
			_, err := m.service.SyncTrackedChartAppNow(ctx, dto.SyncTrackedChartAppRequest{
				AppID:      req.AppID,
				Collection: req.Collection,
				Category:   req.Category,
				Country:    req.Country,
				Lang:       req.Lang,
				Limit:      req.Limit,
			})
			return err
		}
		_, err := m.service.FetchChart(ctx, dto.FetchChartRequest{
			ChartType: req.Collection,
			Category:  req.Category,
			Country:   req.Country,
			Lang:      req.Lang,
			Limit:     req.Limit,
		})
		return err
	case "coverage":
		_, err := m.service.AnalyzeKeywordCoverage(ctx, dto.KeywordCoverageRequest{
			AppID:   req.AppID,
			Country: req.Country,
			Lang:    req.Lang,
			Limit:   req.Limit,
			Deep:    req.Deep,
		})
		return err
	case "reviews":
		fetched, err := m.service.FetchReviews(ctx, dto.FetchReviewsRequest{
			AppID:   req.AppID,
			Country: req.Country,
			Lang:    req.Lang,
			Sort:    "newest",
			Limit:   req.Limit,
		})
		if err != nil {
			return err
		}
		_, err = m.service.SaveReviews(ctx, dto.SaveReviewsRequest{
			AppID:   req.AppID,
			Country: req.Country,
			Lang:    req.Lang,
			Items:   fetched.Items,
		})
		return err
	default:
		return fmt.Errorf("%w: unsupported refresh kind %q", service.ErrInvalidRequest, req.Kind)
	}
}

func refreshJobNow() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func refreshJobID(seq uint64) string {
	return fmt.Sprintf("job-%d-%d", time.Now().UTC().UnixNano(), seq)
}

func refreshWorkerID() string {
	return fmt.Sprintf("worker-%d", time.Now().UTC().UnixNano())
}
