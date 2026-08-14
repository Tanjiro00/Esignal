"use client";

import { useMutation } from "@tanstack/react-query";
import { ArrowRight, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthField } from "@/components/auth-fields";
import { AuthFrame } from "@/components/auth-frame";
import { Button } from "@/components/ui";
import { registerAccount } from "@/lib/api";

function RegisterForm() {
  const searchParams = useSearchParams();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [timezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const registerMutation = useMutation({
    mutationFn: registerAccount,
    onSuccess: (session) => {
      const pendingChannel = searchParams.get("channel")?.trim();
      if (pendingChannel) {
        window.sessionStorage.setItem(
          "earlysignal_pending_channel",
          pendingChannel,
        );
      }
      window.location.assign(session.onboarding_url);
    },
  });
  const passwordValid =
    password.length >= 10 && /[A-Za-z]/.test(password) && /\d/.test(password);

  return (
    <AuthFrame mode="register">
      <form
        className="grid gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          registerMutation.mutate({
            name,
            email,
            password,
            workspace_name: workspaceName,
            timezone,
          });
        }}
      >
        <div className="grid gap-5 sm:grid-cols-2">
          <AuthField
            autoComplete="name"
            label="Your name"
            onChange={(event) => setName(event.target.value)}
            placeholder="Alex Morgan"
            required
            value={name}
          />
          <AuthField
            autoComplete="organization"
            label="Workspace"
            onChange={(event) => setWorkspaceName(event.target.value)}
            placeholder="Channel or team name"
            required
            value={workspaceName}
          />
        </div>
        <AuthField
          autoComplete="email"
          label="Work email"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@channel.com"
          required
          type="email"
          value={email}
        />
        <AuthField
          autoComplete="new-password"
          hint="Use at least 10 characters with a letter and a number."
          label="Password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />

        {registerMutation.isError ? (
          <p
            className="border-l-2 border-[var(--coral)] pl-3 text-[12px] leading-6 text-[var(--coral)]"
            role="alert"
          >
            {registerMutation.error.message}
          </p>
        ) : null}

        <Button
          className="min-h-12 w-full text-[13px]"
          disabled={
            registerMutation.isPending ||
            name.trim().length < 2 ||
            workspaceName.trim().length < 2 ||
            !email ||
            !passwordValid
          }
          type="submit"
          variant="primary"
        >
          {registerMutation.isPending ? (
            <>
              <LoaderCircle className="animate-spin" size={16} /> Creating
              workspace…
            </>
          ) : (
            <>
              Create account <ArrowRight size={15} />
            </>
          )}
        </Button>
      </form>

      <p className="mt-5 text-[10px] leading-5 text-[var(--muted)]">
        EarlySignal uses public YouTube data until you explicitly connect
        read-only Analytics. We never promise a viral result.
      </p>
      <p className="mt-6 border-t border-[var(--line)] pt-6 text-[12px] text-[var(--muted)]">
        Already have an account?{" "}
        <Link
          className="font-semibold text-[var(--ink)] hover:underline"
          href="/login"
        >
          Sign in
        </Link>
      </p>
    </AuthFrame>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-white" />}>
      <RegisterForm />
    </Suspense>
  );
}
