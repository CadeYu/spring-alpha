import GoogleProvider from "next-auth/providers/google";
import type { NextAuthOptions } from "next-auth";

export const visitorCookieName = "spring-alpha-visitor-id";

const googleClientId = process.env.GOOGLE_CLIENT_ID?.trim() ?? "";
const googleClientSecret = process.env.GOOGLE_CLIENT_SECRET?.trim() ?? "";

export const authOptions: NextAuthOptions = {
  providers:
    googleClientId && googleClientSecret
      ? [
          GoogleProvider({
            clientId: googleClientId,
            clientSecret: googleClientSecret,
          }),
        ]
      : [],
  session: {
    strategy: "jwt",
  },
  secret: process.env.NEXTAUTH_SECRET ?? "spring-alpha-dev-secret",
  pages: {
    signIn: "/",
  },
  callbacks: {
    session({ session }) {
      return session;
    },
  },
};
