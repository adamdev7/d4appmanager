export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface Store {
  id: string;
  name: string;
  domain: string;
  status: "connected" | "disconnected" | "pending";
  plan: string;
  timezone: string;
  currency: string;
}

export interface GmailAccount {
  id: string;
  email: string;
  display_name: string;
  status: "connected" | "disconnected" | "expired";
  is_default_sender: boolean;
  store_ids: string[];
}

export interface AppModule {
  id: string;
  name: string;
  description: string;
  slug: string;
  status: "active" | "coming_soon" | "beta" | "setup";
  icon: string;
}
