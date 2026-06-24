package storeintel

import (
	"errors"

	"github.com/catch-radar/storeintel/repo"
	"github.com/catch-radar/storeintel/service"
	"github.com/catch-radar/storeintel/upstream/googleplay"
)

var ErrModuleRepoRequired = errors.New("storeintel repo is required")

type Module struct {
	Service service.StoreIntelService
}

type Dependencies struct {
	Repo           repo.StoreIntelRepo
	Upstream       service.UpstreamClient
	AlertPublisher service.AlertPublisher
	KeywordCorpus  service.KeywordCorpusClient
	Config         service.Config
}

func NewModule(deps Dependencies) (*Module, error) {
	if deps.Repo == nil {
		return nil, ErrModuleRepoRequired
	}
	upstream := deps.Upstream
	if upstream == nil {
		upstream = googleplay.NewClient()
	}
	opts := []service.Option{service.WithConfig(deps.Config)}
	if deps.AlertPublisher != nil {
		opts = append(opts, service.WithAlertPublisher(deps.AlertPublisher))
	}
	if deps.KeywordCorpus != nil {
		opts = append(opts, service.WithKeywordCorpusClient(deps.KeywordCorpus))
	}
	return &Module{
		Service: service.NewStoreIntelService(deps.Repo, upstream, opts...),
	}, nil
}

func NewInMemoryModule(deps Dependencies) *Module {
	if deps.Repo == nil {
		deps.Repo = repo.NewMemoryRepo()
	}
	module, err := NewModule(deps)
	if err != nil {
		panic(err)
	}
	return module
}
