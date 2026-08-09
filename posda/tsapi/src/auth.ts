// Login tokens (stored in redis db 1, like the Python implementation)
// and resolution of the current user for protected routes.

import { RedisClient } from "bun";
import type { Db } from "./db";
import { HttpError, jsonResponse } from "./httpx";
import { passwordIsValid } from "./password";

/** Matches the Python TOKEN_EXPIRE of 1 hour; tokens are re-extended on
 * every authenticated request. */
export const TOKEN_EXPIRE_SECONDS = 3600;

/** Serializes as the /auth/users/me body: key order matters. */
export interface User {
  user_id: number;
  username: string;
  full_name: string | null;
  disabled: boolean | null;
}

interface UserRow extends User {
  hashed_password: string;
}

export class AuthService {
  private redis: RedisClient;

  constructor(
    private db: Db,
    redisHost: string,
    private systemToken: string,
  ) {
    // Login tokens live in redis db 1, separate from other data.
    this.redis = new RedisClient(`redis://${redisHost}:6379/1`, {
      connectionTimeout: 2000,
      enableOfflineQueue: false,
    });
  }

  private async userFromDatabase(
    username: string,
  ): Promise<UserRow | undefined> {
    return this.db.fetchOne<UserRow>(
      `
      select
          user_id,
          user_name as username,
          full_name,
          password as hashed_password,
          disabled
      from auth.users
      where user_name = $1
      `,
      [username],
    );
  }

  /**
   * Resolve a token to a user. The system token is checked before
   * redis so it works even when redis is unavailable.
   */
  async decodeToken(token: string): Promise<UserRow | undefined> {
    if (token === "") return undefined;
    if (token === this.systemToken) return this.userFromDatabase("system");

    let username: string | null;
    try {
      username = await this.redis.get(token);
      if (username === null) return undefined;
      await this.redis.expire(token, TOKEN_EXPIRE_SECONDS);
    } catch (err) {
      console.error(`redis error while resolving token: ${err}`);
      return undefined;
    }
    return this.userFromDatabase(username);
  }

  /**
   * Resolve the logged-in user for a request, throwing the FastAPI
   * auth errors when there is none (Depends(get_current_active_user)).
   */
  async requireUser(req: Request): Promise<User> {
    const row = await this.decodeToken(requestToken(req));
    if (!row) {
      throw new HttpError(401, "Invalid authentication credentials", {
        "WWW-Authenticate": "Bearer",
      });
    }
    if (row.disabled) throw new HttpError(400, "Inactive user");
    return {
      user_id: row.user_id,
      username: row.username,
      full_name: row.full_name,
      disabled: row.disabled,
    };
  }

  /**
   * POST /auth/token: verify the posted form credentials and return a
   * fresh bearer token stored in redis.
   */
  async login(req: Request): Promise<Response> {
    let form: FormData;
    try {
      form = await req.formData();
    } catch {
      throw new HttpError(400, "invalid form data");
    }
    const username = String(form.get("username") ?? "");
    const password = String(form.get("password") ?? "");

    const user = await this.userFromDatabase(username);
    if (!user || !passwordIsValid(user.hashed_password, password)) {
      throw new HttpError(400, "Incorrect username or password");
    }

    const token = crypto.randomUUID();
    await this.redis.set(token, user.username, "EX", TOKEN_EXPIRE_SECONDS);

    return jsonResponse({ access_token: token, token_type: "bearer" });
  }
}

/**
 * Extract the login token from the Authorization header, falling back
 * to the "logintoken" cookie like the Python version.
 */
function requestToken(req: Request): string {
  const authz = req.headers.get("Authorization") ?? "";
  const space = authz.indexOf(" ");
  if (space > 0 && authz.slice(0, space).toLowerCase() === "bearer") {
    return authz.slice(space + 1).trim();
  }
  const cookies = req.headers.get("Cookie") ?? "";
  for (const part of cookies.split(";")) {
    const eq = part.indexOf("=");
    if (eq > 0 && part.slice(0, eq).trim() === "logintoken") {
      return part.slice(eq + 1).trim();
    }
  }
  return "";
}
