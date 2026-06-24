package schema

import (
	"strings"
	"testing"
)

func TestSplitSQLStatementsUsesEmbeddedMySQLSchema(t *testing.T) {
	statements := splitSQLStatements(MySQL)
	if got, want := len(statements), 14; got != want {
		t.Fatalf("statement count = %d, want %d", got, want)
	}
	if !strings.Contains(statements[0], "CREATE TABLE IF NOT EXISTS `store_intel_apps`") {
		t.Fatalf("first statement does not create apps table: %s", statements[0])
	}
	if !strings.Contains(statements[len(statements)-1], "CREATE TABLE IF NOT EXISTS `store_intel_settings`") {
		t.Fatalf("last statement does not create settings table: %s", statements[len(statements)-1])
	}
}
