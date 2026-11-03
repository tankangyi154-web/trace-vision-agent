CREATE TABLE gateway_users (user_key TEXT PRIMARY KEY NOT NULL, used INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
--> statement-breakpoint
CREATE TABLE gateway_quotas (quota_key TEXT PRIMARY KEY NOT NULL, used INTEGER NOT NULL DEFAULT 0);
--> statement-breakpoint
CREATE TABLE gateway_questions (id TEXT PRIMARY KEY NOT NULL, user_key TEXT NOT NULL, day_key TEXT NOT NULL, month_key TEXT NOT NULL, counted INTEGER NOT NULL DEFAULT 0, model_calls INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL);
--> statement-breakpoint
CREATE INDEX gateway_questions_expiry ON gateway_questions (expires_at);
