package schema

import (
	"context"
	"database/sql"
	_ "embed"
	"strings"
)

//go:embed mysql.sql
var MySQL string

func ApplyMySQL(ctx context.Context, db *sql.DB) error {
	for _, statement := range splitSQLStatements(MySQL) {
		if _, err := db.ExecContext(ctx, statement); err != nil {
			return err
		}
	}
	return nil
}

func splitSQLStatements(script string) []string {
	parts := strings.Split(script, ";")
	statements := make([]string, 0, len(parts))
	for _, part := range parts {
		statement := strings.TrimSpace(part)
		if statement == "" {
			continue
		}
		statements = append(statements, statement)
	}
	return statements
}
