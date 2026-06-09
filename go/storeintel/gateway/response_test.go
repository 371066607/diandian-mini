package gateway_test

import (
	"errors"
	"testing"

	"github.com/diandian-mini/storeintel/dto"
	"github.com/diandian-mini/storeintel/gateway"
	"github.com/diandian-mini/storeintel/service"
)

func TestSuccessWithContextMatchesGatewayEnvelope(t *testing.T) {
	resp := gateway.SuccessWithContext(map[string]any{"ok": true}, dto.RequestContext{
		RequestID: "req-1",
		TraceID:   "trace-1",
	})
	if resp.Code != gateway.ErrorCodeOK || resp.Message != "success" {
		t.Fatalf("unexpected response: %+v", resp)
	}
	if resp.RequestID != "req-1" || resp.TraceID != "trace-1" {
		t.Fatalf("trace context not copied: %+v", resp)
	}
}

func TestMapServiceError(t *testing.T) {
	httpStatus, code, _, errorCode := gateway.MapServiceError(service.ErrInvalidRequest)
	if httpStatus != 400 || code != gateway.ErrorCodeBadRequest || errorCode != "STORE_INTEL_REQUEST_INVALID" {
		t.Fatalf("bad invalid-request mapping: %d %d %s", httpStatus, code, errorCode)
	}

	httpStatus, code, _, errorCode = gateway.MapServiceError(errors.New("boom"))
	if httpStatus != 500 || code != gateway.ErrorCodeInternalFailure || errorCode != "STORE_INTEL_INTERNAL_ERROR" {
		t.Fatalf("bad fallback mapping: %d %d %s", httpStatus, code, errorCode)
	}
}
