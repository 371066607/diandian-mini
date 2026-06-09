package storeintel_test

import (
	"context"
	"testing"

	storeintel "github.com/diandian-mini/storeintel"
	"github.com/diandian-mini/storeintel/dto"
	"github.com/diandian-mini/storeintel/repo"
)

type moduleFakeUpstream struct{}

func (moduleFakeUpstream) SearchApps(context.Context, dto.SearchAppsRequest) ([]dto.AppSummary, error) {
	return []dto.AppSummary{{Platform: dto.PlatformGooglePlay, AppID: "com.demo"}}, nil
}

func (moduleFakeUpstream) GetAppDetail(context.Context, dto.GetAppDetailRequest) (dto.AppDetail, error) {
	return dto.AppDetail{AppSummary: dto.AppSummary{Platform: dto.PlatformGooglePlay, AppID: "com.demo", Title: "Demo"}}, nil
}

func TestNewModuleExposesCallableService(t *testing.T) {
	module, err := storeintel.NewModule(storeintel.Dependencies{
		Repo:     repo.NewMemoryRepo(),
		Upstream: moduleFakeUpstream{},
	})
	if err != nil {
		t.Fatalf("NewModule returned error: %v", err)
	}
	result, err := module.Service.SearchApps(context.Background(), dto.SearchAppsRequest{Query: "demo"})
	if err != nil {
		t.Fatalf("SearchApps returned error: %v", err)
	}
	if result.Total != 1 || result.Items[0].AppID != "com.demo" {
		t.Fatalf("unexpected result: %+v", result)
	}
}
