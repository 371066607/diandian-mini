package gateway

import (
	"errors"
	"net/http"

	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/service"
)

const (
	ErrorCodeOK              = 200
	ErrorCodeBadRequest      = 400
	ErrorCodeUnauthorized    = 401
	ErrorCodeForbidden       = 403
	ErrorCodeNotFound        = 404
	ErrorCodeConflict        = 409
	ErrorCodeTooManyRequests = 429
	ErrorCodeInternalFailure = 500
)

type Response[T any] struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	Data      T      `json:"data"`
	TraceID   string `json:"trace_id,omitempty"`
	RequestID string `json:"request_id,omitempty"`
}

func Success[T any](data T) Response[T] {
	return Response[T]{Code: ErrorCodeOK, Message: "success", Data: data}
}

func SuccessWithContext[T any](data T, ctx dto.RequestContext) Response[T] {
	resp := Success(data)
	resp.TraceID = ctx.TraceID
	resp.RequestID = ctx.RequestID
	return resp
}

func Failure(code int, message, errorCode string) Response[map[string]any] {
	return Response[map[string]any]{
		Code:    code,
		Message: message,
		Data:    map[string]any{"error_code": errorCode},
	}
}

func FailureWithContext(code int, message, errorCode string, ctx dto.RequestContext) Response[map[string]any] {
	resp := Failure(code, message, errorCode)
	resp.TraceID = ctx.TraceID
	resp.RequestID = ctx.RequestID
	return resp
}

func MapServiceError(err error) (httpStatus int, code int, message string, errorCode string) {
	switch {
	case err == nil:
		return http.StatusOK, ErrorCodeOK, "success", ""
	case errors.Is(err, service.ErrInvalidRequest):
		return http.StatusBadRequest, ErrorCodeBadRequest, err.Error(), "STORE_INTEL_REQUEST_INVALID"
	case errors.Is(err, service.ErrNotFound):
		return http.StatusNotFound, ErrorCodeNotFound, err.Error(), "STORE_INTEL_NOT_FOUND"
	case errors.Is(err, service.ErrServiceUnavailable):
		return http.StatusBadGateway, ErrorCodeInternalFailure, "store intel service is not configured", "STORE_INTEL_SERVICE_NOT_CONFIGURED"
	case errors.Is(err, service.ErrUpstreamUnavailable):
		return http.StatusBadGateway, ErrorCodeInternalFailure, "store intel upstream failed", "STORE_INTEL_UPSTREAM_FAILED"
	default:
		return http.StatusInternalServerError, ErrorCodeInternalFailure, "internal error", "STORE_INTEL_INTERNAL_ERROR"
	}
}
