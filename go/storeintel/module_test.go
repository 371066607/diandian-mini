package storeintel_test

import (
	"context"
	"testing"

	storeintel "github.com/catch-radar/storeintel"
	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/repo"
)

type moduleFakeUpstream struct{}

func (moduleFakeUpstream) SearchApps(context.Context, dto.SearchAppsRequest) ([]dto.AppSummary, error) {
	return []dto.AppSummary{{Platform: dto.PlatformGooglePlay, AppID: "com.demo"}}, nil
}

func (moduleFakeUpstream) Suggest(context.Context, dto.SuggestRequest) ([]string, error) {
	return []string{"demo app"}, nil
}

func (moduleFakeUpstream) GetAppDetail(context.Context, dto.GetAppDetailRequest) (dto.AppDetail, error) {
	return dto.AppDetail{AppSummary: dto.AppSummary{Platform: dto.PlatformGooglePlay, AppID: "com.demo", Title: "Demo"}}, nil
}

func (moduleFakeUpstream) SimilarApps(context.Context, dto.SimilarAppsRequest) ([]dto.AppSummary, error) {
	return []dto.AppSummary{{Platform: dto.PlatformGooglePlay, AppID: "com.related"}}, nil
}

func (moduleFakeUpstream) GetAppPermissions(context.Context, dto.AppPermissionsRequest) (map[string][]string, error) {
	return map[string][]string{"Location": {"approximate location"}}, nil
}

func (moduleFakeUpstream) FetchChart(context.Context, dto.FetchChartRequest) (dto.FetchChartResponse, error) {
	return dto.FetchChartResponse{}, nil
}

func (moduleFakeUpstream) FetchReviews(context.Context, dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error) {
	return dto.FetchReviewsResponse{}, nil
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
