"use client";

import { useMutation } from "@tanstack/react-query";
import { ArrowRight, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthField } from "@/components/auth-fields";
import { AuthFrame } from "@/components/auth-frame";
import { Button } from "@/components/ui";
import { loginAccount } from "@/lib/api";

function safeNext(value: string | null) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/today";
}

function LoginForm() {
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const loginMutation = useMutation({
    mutationFn: loginAccount,
    onSuccess: (session) => {
      const requested = safeNext(searchParams.get("next"));
      const destination =
        session.workspace.onboarding_status === "completed"
          ? requested
          : session.onboarding_url;
      window.location.assign(destination);
    },
  });

  return (
    <AuthFrame mode="login">
      <form
        className="grid gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          loginMutation.mutate({ email, password });
        }}
      >
        <AuthField
          autoComplete="email"
          label="Email"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@channel.com"
          required
          type="email"
          value={email}
        />
        <AuthField
          autoComplete="current-password"
          label="Password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />

        {loginMutation.isError ? (
          <p
            className="border-l-2 border-[var(--coral)] pl-3 text-[12px] leading-6 text-[var(--coral)]"
            role="alert"
          >
            {loginMutation.error.message}
          </p>
        ) : null}

        <Button
          className="min-h-12 w-full text-[13px]"
          disabled={loginMutation.isPending || !email || !password}
          type="submit"
          variant="primary"
        >
          {loginMutation.isPending ? (
            <>
              <LoaderCircle className="animate-spin" size={16} /> Signing in…
            </>
          ) : (
            <>
              Sign in <ArrowRight size={15} />
            </>
          )}
        </Button>
      </form>

      <p className="mt-7 border-t border-[var(--line)] pt-6 text-[12px] text-[var(--muted)]">
        New to EarlySignal?{" "}
        <Link
          className="font-semibold text-[var(--ink)] hover:underline"
          href="/register"
        >
          Create an account
        </Link>
      </p>
    </AuthFrame>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-white" />}>
      <LoginForm />
    </Suspense>
  );
}
