/** Tipos de autenticación de `services/api` (`/auth`). */
export type UserRole = "admin" | "manager" | "user";

export interface Profile {
  id: string;
  user_id: string;
  name: string | null;
  phone: string | null;
  address: string | null;
}

/** Respuesta de `GET /auth/me`. Nunca incluye el hash de la contraseña. */
export interface CurrentUser {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  profile: Profile;
}

/** Cuerpo de `POST /users` (registro público). La API siempre crea el usuario con rol `user`. */
export interface RegisterPayload {
  email: string;
  password: string;
  name?: string;
  phone?: string;
  address?: string;
  /** Obligatorio solo si la API tiene configurada `REGISTRATION_CODE`. */
  invitation_code?: string;
}

/** Cuerpo de `PUT /profiles/me`: solo los datos de contacto. `null` vacía el campo. */
export interface ProfileUpdate {
  name: string | null;
  phone: string | null;
  address: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  /** Segundos de validez del token. */
  expires_in: number;
}
