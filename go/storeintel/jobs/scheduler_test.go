package jobs

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/catch-radar/storeintel/dto"
)

type fakeSchedulerService struct {
	settings     map[string]string
	settingsErr  error
	acquireErr   error
	syncErr      error
	cleanupErr   error
	acquireCalls int
	syncCalls    int
	cleanupCalls int
	lastDueOnly  bool
}

func (f *fakeSchedulerService) GetSettings(context.Context) (map[string]string, error) {
	if f.settingsErr != nil {
		return nil, f.settingsErr
	}
	return f.settings, nil
}

func (f *fakeSchedulerService) AcquireSettingValue(_ context.Context, key, value string) (bool, error) {
	f.acquireCalls++
	if f.acquireErr != nil {
		return false, f.acquireErr
	}
	if f.settings == nil {
		f.settings = map[string]string{}
	}
	if f.settings[key] == value {
		return false, nil
	}
	f.settings[key] = value
	return true, nil
}

func (f *fakeSchedulerService) SyncAll(_ context.Context, req dto.SyncAllRequest) (dto.SyncAllResponse, error) {
	f.syncCalls++
	f.lastDueOnly = req.DueOnly
	return dto.SyncAllResponse{AppsSynced: 1}, f.syncErr
}

func (f *fakeSchedulerService) CleanupHistory(context.Context) (dto.HistoryRetentionCleanupResponse, error) {
	f.cleanupCalls++
	return dto.HistoryRetentionCleanupResponse{}, f.cleanupErr
}

func TestSchedulerRunDueRunsOncePerDay(t *testing.T) {
	service := &fakeSchedulerService{settings: map[string]string{
		"scheduler_enabled": "true",
		"daily_sync_time":   "09:30",
	}}
	scheduler := NewScheduler(service)
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.Local)

	ran, err := scheduler.RunDue(context.Background(), now)
	if err != nil || !ran {
		t.Fatalf("first RunDue ran=%v err=%v", ran, err)
	}
	if service.syncCalls != 1 || service.cleanupCalls != 1 || !service.lastDueOnly {
		t.Fatalf("sync/cleanup not called as expected: %+v", service)
	}
	if service.settings[schedulerLastRunDayKey] != "2026-06-18" {
		t.Fatalf("scheduler run day not persisted: %+v", service.settings)
	}

	ran, err = scheduler.RunDue(context.Background(), now.Add(30*time.Second))
	if err != nil || ran {
		t.Fatalf("second same-day RunDue ran=%v err=%v", ran, err)
	}
	if service.syncCalls != 1 {
		t.Fatalf("same-day run duplicated sync: %d", service.syncCalls)
	}

	ran, err = scheduler.RunDue(context.Background(), now.Add(24*time.Hour))
	if err != nil || !ran || service.syncCalls != 2 {
		t.Fatalf("next-day RunDue ran=%v syncCalls=%d err=%v", ran, service.syncCalls, err)
	}
}

func TestSchedulerRunDueSkipsPersistedRunDayAfterRestart(t *testing.T) {
	service := &fakeSchedulerService{settings: map[string]string{
		"scheduler_enabled":    "true",
		"daily_sync_time":      "09:00",
		schedulerLastRunDayKey: "2026-06-18",
	}}
	restarted := NewScheduler(service)

	ran, err := restarted.RunDue(context.Background(), time.Date(2026, 6, 18, 9, 0, 0, 0, time.Local))
	if err != nil || ran {
		t.Fatalf("persisted run day should skip after restart: ran=%v err=%v", ran, err)
	}
	if service.syncCalls != 0 || service.acquireCalls != 1 {
		t.Fatalf("persisted run day should not sync and should reject acquire: sync=%d acquire=%d", service.syncCalls, service.acquireCalls)
	}
}

func TestSchedulerRunDueDoesNotSyncWhenRunDayAcquireFails(t *testing.T) {
	service := &fakeSchedulerService{
		settings: map[string]string{
			"scheduler_enabled": "true",
			"daily_sync_time":   "09:00",
		},
		acquireErr: errors.New("settings boom"),
	}
	scheduler := NewScheduler(service)

	ran, err := scheduler.RunDue(context.Background(), time.Date(2026, 6, 18, 9, 0, 0, 0, time.Local))
	if err == nil || ran {
		t.Fatalf("settings failure should block scheduled sync: ran=%v err=%v", ran, err)
	}
	if service.syncCalls != 0 || service.cleanupCalls != 0 {
		t.Fatalf("sync/cleanup should not run when ledger write fails: sync=%d cleanup=%d", service.syncCalls, service.cleanupCalls)
	}
}

func TestSchedulerRunDueHonorsDisabledAndMalformedTimeFallback(t *testing.T) {
	disabled := &fakeSchedulerService{settings: map[string]string{
		"scheduler_enabled": "false",
		"daily_sync_time":   "09:00",
	}}
	scheduler := NewScheduler(disabled)
	ran, err := scheduler.RunDue(context.Background(), time.Date(2026, 6, 18, 9, 0, 0, 0, time.Local))
	if err != nil || ran || disabled.syncCalls != 0 {
		t.Fatalf("disabled scheduler should not run: ran=%v calls=%d err=%v", ran, disabled.syncCalls, err)
	}

	malformed := &fakeSchedulerService{settings: map[string]string{
		"scheduler_enabled": "true",
		"daily_sync_time":   "not-a-time",
	}}
	scheduler = NewScheduler(malformed)
	ran, err = scheduler.RunDue(context.Background(), time.Date(2026, 6, 18, 9, 0, 0, 0, time.Local))
	if err != nil || !ran || malformed.syncCalls != 1 {
		t.Fatalf("malformed time should fall back to 09:00: ran=%v calls=%d err=%v", ran, malformed.syncCalls, err)
	}
}

func TestSchedulerRunDueSkipsCleanupWhenSyncFails(t *testing.T) {
	service := &fakeSchedulerService{
		settings: map[string]string{
			"scheduler_enabled": "true",
			"daily_sync_time":   "09:00",
		},
		syncErr: errors.New("boom"),
	}
	scheduler := NewScheduler(service)
	ran, err := scheduler.RunDue(context.Background(), time.Date(2026, 6, 18, 9, 0, 0, 0, time.Local))
	if err == nil || !ran {
		t.Fatalf("sync failure should be returned after scheduled run: ran=%v err=%v", ran, err)
	}
	if service.syncCalls != 1 || service.cleanupCalls != 0 {
		t.Fatalf("cleanup should be skipped on sync error: sync=%d cleanup=%d", service.syncCalls, service.cleanupCalls)
	}
}

func TestSchedulerRunDueIgnoresCleanupFailure(t *testing.T) {
	service := &fakeSchedulerService{
		settings: map[string]string{
			"scheduler_enabled": "true",
			"daily_sync_time":   "09:00",
		},
		cleanupErr: errors.New("cleanup boom"),
	}
	scheduler := NewScheduler(service, WithLogger(nil))
	ran, err := scheduler.RunDue(context.Background(), time.Date(2026, 6, 18, 9, 0, 0, 0, time.Local))
	if err != nil || !ran || service.cleanupCalls != 1 {
		t.Fatalf("cleanup failure should not fail sync: ran=%v cleanup=%d err=%v", ran, service.cleanupCalls, err)
	}
}
