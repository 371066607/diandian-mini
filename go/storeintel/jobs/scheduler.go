package jobs

import (
	"context"
	"log"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/catch-radar/storeintel/dto"
)

type SchedulerService interface {
	GetSettings(ctx context.Context) (map[string]string, error)
	AcquireSettingValue(ctx context.Context, key, value string) (bool, error)
	SyncAll(ctx context.Context, req dto.SyncAllRequest) (dto.SyncAllResponse, error)
	CleanupHistory(ctx context.Context) (dto.HistoryRetentionCleanupResponse, error)
}

const schedulerLastRunDayKey = "scheduler_last_run_day"

type Scheduler struct {
	service    SchedulerService
	interval   time.Duration
	now        func() time.Time
	logger     *log.Logger
	lastRunDay string

	mu      sync.Mutex
	running bool
	stop    chan struct{}
	done    chan struct{}
}

type SchedulerOption func(*Scheduler)

func NewScheduler(service SchedulerService, opts ...SchedulerOption) *Scheduler {
	scheduler := &Scheduler{
		service:  service,
		interval: time.Minute,
		now:      time.Now,
		logger:   log.Default(),
	}
	for _, opt := range opts {
		if opt != nil {
			opt(scheduler)
		}
	}
	if scheduler.interval <= 0 {
		scheduler.interval = time.Minute
	}
	if scheduler.now == nil {
		scheduler.now = time.Now
	}
	return scheduler
}

func WithInterval(interval time.Duration) SchedulerOption {
	return func(s *Scheduler) {
		s.interval = interval
	}
}

func WithNow(now func() time.Time) SchedulerOption {
	return func(s *Scheduler) {
		s.now = now
	}
}

func WithLogger(logger *log.Logger) SchedulerOption {
	return func(s *Scheduler) {
		s.logger = logger
	}
}

func (s *Scheduler) Start(ctx context.Context) {
	if s == nil || s.service == nil {
		return
	}
	s.mu.Lock()
	if s.running {
		s.mu.Unlock()
		return
	}
	s.running = true
	s.stop = make(chan struct{})
	s.done = make(chan struct{})
	stop := s.stop
	done := s.done
	s.mu.Unlock()

	go s.loop(ctx, stop, done)
}

func (s *Scheduler) Stop() {
	if s == nil {
		return
	}
	s.mu.Lock()
	if !s.running {
		s.mu.Unlock()
		return
	}
	stop := s.stop
	done := s.done
	s.running = false
	s.stop = nil
	s.done = nil
	close(stop)
	s.mu.Unlock()
	<-done
}

func (s *Scheduler) RunDue(ctx context.Context, now time.Time) (bool, error) {
	if s == nil || s.service == nil {
		return false, nil
	}
	settings, err := s.service.GetSettings(ctx)
	if err != nil {
		return false, err
	}
	if strings.ToLower(strings.TrimSpace(settings["scheduler_enabled"])) != "true" {
		return false, nil
	}
	hour, minute := parseTimeOfDay(settings["daily_sync_time"])
	local := now.Local()
	if local.Hour() != hour || local.Minute() != minute {
		return false, nil
	}
	day := local.Format("2006-01-02")
	s.mu.Lock()
	if s.lastRunDay == day {
		s.mu.Unlock()
		return false, nil
	}
	s.lastRunDay = day
	s.mu.Unlock()

	acquired, err := s.service.AcquireSettingValue(ctx, schedulerLastRunDayKey, day)
	if err != nil {
		s.mu.Lock()
		if s.lastRunDay == day {
			s.lastRunDay = ""
		}
		s.mu.Unlock()
		return false, err
	}
	if !acquired {
		return false, nil
	}

	if _, err := s.service.SyncAll(ctx, dto.SyncAllRequest{DueOnly: true}); err != nil {
		return true, err
	}
	if _, err := s.service.CleanupHistory(ctx); err != nil && s.logger != nil {
		s.logger.Printf("storeintel scheduler: history cleanup failed: %v", err)
	}
	return true, nil
}

func (s *Scheduler) loop(ctx context.Context, stop <-chan struct{}, done chan<- struct{}) {
	defer close(done)
	ticker := time.NewTicker(s.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-stop:
			return
		case now := <-ticker.C:
			s.runAndLog(ctx, now)
		}
	}
}

func (s *Scheduler) runAndLog(ctx context.Context, now time.Time) {
	ran, err := s.RunDue(ctx, now)
	if err != nil && s.logger != nil {
		s.logger.Printf("storeintel scheduler: sync failed: %v", err)
	}
	if ran && err == nil && s.logger != nil {
		s.logger.Print("storeintel scheduler: sync completed")
	}
}

func parseTimeOfDay(value string) (int, int) {
	parts := strings.Split(strings.TrimSpace(value), ":")
	if len(parts) != 2 {
		return 9, 0
	}
	hour, hourErr := strconv.Atoi(parts[0])
	minute, minuteErr := strconv.Atoi(parts[1])
	if hourErr != nil || minuteErr != nil || hour < 0 || hour > 23 || minute < 0 || minute > 59 {
		return 9, 0
	}
	return hour, minute
}
