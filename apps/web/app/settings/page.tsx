"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Check,
  KeyRound,
  Link2,
  LogOut,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Unplug,
  Youtube,
} from "lucide-react";
import { useState } from "react";

import { Button, ErrorState, PageLoading } from "@/components/ui";
import {
  addMonitoredChannel,
  changeAccountPassword,
  disconnectYoutubeOAuth,
  getChannelProfile,
  getDemoContext,
  getDigestSubscription,
  getWorkspaceChannels,
  getYoutubeOAuthStatus,
  logoutAccount,
  startYoutubeOAuth,
  syncYoutubeAnalytics,
  updateChannelProfile,
  updateDigestSubscription,
  updateMonitoredChannel,
} from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type {
  ChannelProfile,
  DemoContext,
  DigestSubscription,
  MonitoredChannel,
  YoutubeOAuthStatus,
} from "@/lib/types";

type SettingsData = {
  context: DemoContext;
  profile: ChannelProfile;
  oauth: YoutubeOAuthStatus;
  channels: MonitoredChannel[];
  subscription: DigestSubscription;
};

function commaList(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function channelIdFromInput(value: string) {
  const channelMatch = value.match(/youtube\.com\/channel\/([^/?#]+)/i);
  if (channelMatch?.[1]) return channelMatch[1].trim();
  const handleMatch = value.match(/youtube\.com\/(@[^/?#]+)/i);
  return (handleMatch?.[1] ?? value).trim();
}

function profilePayload(profile: ChannelProfile, data: FormData) {
  return {
    audience_description: String(
      data.get("audience_description") ?? profile.audience_description,
    ),
    geography: profile.geography,
    language: profile.language,
    topic_keywords: profile.topic_keywords,
    core_topics: commaList(data.get("core_topics")),
    adjacent_topics: commaList(data.get("adjacent_topics")),
    preferred_formats: commaList(data.get("preferred_formats")),
    creator_expertise: profile.creator_expertise,
    production_capabilities: profile.production_capabilities,
    exclusions: commaList(data.get("exclusions")),
    strategic_goals: commaList(data.get("strategic_goals")),
    normal_duration_min_seconds: profile.normal_duration_min_seconds,
    normal_duration_max_seconds: profile.normal_duration_max_seconds,
    production_days_min: Number(
      data.get("production_days_min") ?? profile.production_days_min,
    ),
    production_days_max: Number(
      data.get("production_days_max") ?? profile.production_days_max,
    ),
    audience_sophistication: profile.audience_sophistication,
    creator_authority: profile.creator_authority,
    risk_tolerance: String(
      data.get("risk_tolerance") ?? profile.risk_tolerance,
    ) as ChannelProfile["risk_tolerance"],
    team_size: Number(data.get("team_size") ?? profile.team_size),
    research_capacity_hours: Number(
      data.get("research_capacity_hours") ?? profile.research_capacity_hours,
    ),
    filming_required: profile.filming_required,
    external_guests_required: profile.external_guests_required,
    editing_complexity: String(
      data.get("editing_complexity") ?? profile.editing_complexity,
    ) as ChannelProfile["editing_complexity"],
    access_to_products: profile.access_to_products,
    experiment_level: String(
      data.get("experiment_level") ?? profile.experiment_level,
    ) as ChannelProfile["experiment_level"],
    evergreen_trend_balance: Number(
      data.get("evergreen_trend_balance") ?? profile.evergreen_trend_balance,
    ),
    weekday_publish_only: profile.weekday_publish_only,
    content_calendar: profile.content_calendar,
  };
}

function Field({
  label,
  name,
  defaultValue,
  hint,
}: {
  label: string;
  name: string;
  defaultValue: string;
  hint?: string;
}) {
  return (
    <label className="block text-[12px] font-medium">
      {label}
      <textarea
        className="mt-2 min-h-20 w-full resize-y border border-[var(--line-strong)] bg-white p-3 text-[12px] leading-6 font-normal outline-none focus:border-[var(--ink)]"
        defaultValue={defaultValue}
        name={name}
      />
      {hint ? (
        <span className="mt-1 block text-[10px] font-normal text-[var(--muted)]">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

export default function SettingsPage() {
  const client = useQueryClient();
  const [channelInput, setChannelInput] = useState("");
  const [cadence, setCadence] =
    useState<DigestSubscription["cadence"]>("twice_weekly");
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const query = useQuery<SettingsData>({
    queryKey: ["settings-v2"],
    queryFn: async () => {
      const context = await getDemoContext();
      const [profile, oauth, channels, subscription] = await Promise.all([
        getChannelProfile(context.workspace_id),
        getYoutubeOAuthStatus(context.workspace_id),
        getWorkspaceChannels(context.workspace_id),
        getDigestSubscription(context.workspace_id),
      ]);
      setCadence(subscription.cadence);
      setNotificationsEnabled(subscription.enabled);
      return { context, profile, oauth, channels, subscription };
    },
  });
  const profileMutation = useMutation({
    mutationFn: (payload: Parameters<typeof updateChannelProfile>[1]) =>
      updateChannelProfile(query.data!.context.workspace_id, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["settings-v2"] }),
  });
  const channelMutation = useMutation({
    mutationFn: () =>
      addMonitoredChannel(
        query.data!.context.workspace_id,
        channelIdFromInput(channelInput),
        "reference",
      ),
    onSuccess: () => {
      setChannelInput("");
      client.invalidateQueries({ queryKey: ["settings-v2"] });
    },
  });
  const channelToggleMutation = useMutation({
    mutationFn: ({
      channelId,
      active,
    }: {
      channelId: string;
      active: boolean;
    }) =>
      updateMonitoredChannel(
        query.data!.context.workspace_id,
        channelId,
        active,
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["settings-v2"] }),
  });
  const notificationMutation = useMutation({
    mutationFn: () =>
      updateDigestSubscription(query.data!.context.workspace_id, {
        cadence,
        delivery_channel: "in_app",
        destination: query.data!.subscription.destination,
        enabled: notificationsEnabled,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["settings-v2"] }),
  });
  const oauthMutation = useMutation({
    mutationFn: async (action: "connect" | "sync" | "disconnect") => {
      const workspaceId = query.data!.context.workspace_id;
      if (action === "connect") {
        const response = await startYoutubeOAuth(workspaceId);
        window.location.assign(response.authorization_url);
        return response;
      }
      if (action === "sync") return syncYoutubeAnalytics(workspaceId);
      return disconnectYoutubeOAuth(workspaceId);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["settings-v2"] }),
  });
  const passwordMutation = useMutation({
    mutationFn: () =>
      changeAccountPassword({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    },
  });
  const logoutMutation = useMutation({
    mutationFn: logoutAccount,
    onSettled: () => {
      client.clear();
      window.location.assign("/login");
    },
  });

  if (query.isLoading) return <PageLoading label="Loading settings" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const { profile, oauth, channels, subscription } = query.data;
  const owned = channels.find((channel) => channel.relationship === "owned");
  const references = channels.filter(
    (channel) => channel.relationship !== "owned",
  );
  const selectedReferences = references.filter((channel) => channel.active);

  return (
    <div className="mx-auto max-w-[1080px] px-5 py-8 sm:px-8 sm:py-12">
      <header className="border-b border-[var(--ink)] pb-8">
        <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
          Personalize recommendations
        </p>
        <h1 className="editorial mt-3 text-[46px] leading-none sm:text-[62px]">
          Settings
        </h1>
        <p className="mt-4 max-w-[680px] text-[14px] leading-7 text-[var(--muted)]">
          Tell EarlySignal what fits your audience, what your team can produce
          and which channels define your niche.
        </p>
        <nav
          aria-label="Settings sections"
          className="mt-6 flex gap-x-5 gap-y-2 overflow-x-auto text-[11px] font-medium"
        >
          <a className="min-h-10 shrink-0 py-3 hover:underline" href="#account">
            Account
          </a>
          <a
            className="min-h-10 shrink-0 py-3 hover:underline"
            href="#channel-profile"
          >
            Channel fit
          </a>
          <a
            className="min-h-10 shrink-0 py-3 hover:underline"
            href="#production"
          >
            Production
          </a>
          <a
            className="min-h-10 shrink-0 py-3 hover:underline"
            href="#monitored-channels"
          >
            Monitored channels
          </a>
          <a
            className="min-h-10 shrink-0 py-3 hover:underline"
            href="#notifications"
          >
            Notifications
          </a>
          <a
            className="min-h-10 shrink-0 py-3 hover:underline"
            href="#connections"
          >
            Connections
          </a>
        </nav>
      </header>

      <section
        className="scroll-mt-6 border-b border-[var(--line-strong)] py-9"
        id="account"
      >
        <div className="flex items-start gap-3">
          <KeyRound className="mt-1 text-[var(--lime-strong)]" size={20} />
          <div>
            <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
              Account
            </p>
            <h2 className="editorial mt-2 text-[32px]">
              {query.data.context.user_name}
            </h2>
            <p className="mt-2 text-[12px] text-[var(--muted)]">
              {query.data.context.user_email} ·{" "}
              {query.data.context.workspace_name}
            </p>
          </div>
        </div>
        <form
          className="mt-7 grid gap-4 sm:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (newPassword !== confirmPassword) return;
            passwordMutation.mutate();
          }}
        >
          <label className="text-[12px] font-medium">
            Current password
            <input
              autoComplete="current-password"
              className="mt-2 h-11 w-full border border-[var(--line-strong)] px-3 font-normal"
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
              type="password"
              value={currentPassword}
            />
          </label>
          <label className="text-[12px] font-medium">
            New password
            <input
              autoComplete="new-password"
              className="mt-2 h-11 w-full border border-[var(--line-strong)] px-3 font-normal"
              minLength={10}
              onChange={(event) => setNewPassword(event.target.value)}
              required
              type="password"
              value={newPassword}
            />
          </label>
          <label className="text-[12px] font-medium">
            Confirm new password
            <input
              autoComplete="new-password"
              className="mt-2 h-11 w-full border border-[var(--line-strong)] px-3 font-normal"
              minLength={10}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              type="password"
              value={confirmPassword}
            />
          </label>
          <div className="sm:col-span-3">
            {newPassword &&
            confirmPassword &&
            newPassword !== confirmPassword ? (
              <p className="mb-3 text-[11px] text-[var(--danger)]">
                Passwords do not match.
              </p>
            ) : null}
            {passwordMutation.isError ? (
              <p className="mb-3 text-[11px] text-[var(--danger)]">
                {passwordMutation.error.message}
              </p>
            ) : null}
            {passwordMutation.isSuccess ? (
              <p className="mb-3 text-[11px] text-[var(--lime-ink)]">
                Password changed. Other signed-in sessions were closed.
              </p>
            ) : null}
            <Button
              disabled={
                passwordMutation.isPending ||
                newPassword.length < 10 ||
                newPassword !== confirmPassword
              }
              type="submit"
              variant="primary"
            >
              {passwordMutation.isPending ? "Updating…" : "Change password"}
            </Button>
          </div>
        </form>
        <button
          className="mt-6 flex min-h-11 items-center gap-2 text-[12px] font-semibold text-[var(--coral)]"
          disabled={logoutMutation.isPending}
          onClick={() => logoutMutation.mutate()}
          type="button"
        >
          <LogOut size={15} />
          {logoutMutation.isPending ? "Signing out…" : "Sign out"}
        </button>
      </section>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          profileMutation.mutate(
            profilePayload(profile, new FormData(event.currentTarget)),
          );
        }}
      >
        <section
          className="scroll-mt-6 border-b border-[var(--line-strong)] py-9"
          id="channel-profile"
        >
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                Channel fit
              </p>
              <h2 className="editorial mt-2 text-[32px]">
                What belongs on {profile.channel_title}?
              </h2>
              <p className="mt-2 max-w-[650px] text-[12px] leading-6 text-[var(--muted)]">
                These explicit choices override assumptions inferred from old
                uploads.
              </p>
            </div>
            <Button
              className="min-h-11"
              disabled={profileMutation.isPending}
              type="submit"
              variant="primary"
            >
              <Save size={14} />
              {profileMutation.isPending ? "Recalculating…" : "Save profile"}
            </Button>
          </div>

          <div className="mt-7 grid gap-5 sm:grid-cols-2">
            <label className="block text-[12px] font-medium sm:col-span-2">
              Audience
              <textarea
                className="mt-2 min-h-24 w-full border border-[var(--line-strong)] p-3 text-[12px] leading-6 font-normal outline-none focus:border-[var(--ink)]"
                defaultValue={profile.audience_description}
                name="audience_description"
              />
            </label>
            <Field
              defaultValue={profile.core_topics.join(", ")}
              hint="Topics you actively want to grow."
              label="Core topics"
              name="core_topics"
            />
            <Field
              defaultValue={profile.adjacent_topics.join(", ")}
              hint="Credible extensions, not the main strategy."
              label="Adjacent topics"
              name="adjacent_topics"
            />
            <Field
              defaultValue={profile.preferred_formats.join(", ")}
              hint="Formats your team can repeat reliably."
              label="Formats that fit"
              name="preferred_formats"
            />
            <Field
              defaultValue={profile.strategic_goals.join(", ")}
              hint="What the channel should become known for."
              label="Strategic goals"
              name="strategic_goals"
            />
            <Field
              defaultValue={profile.exclusions.join(", ")}
              hint="Topics and claims EarlySignal should avoid."
              label="Never recommend"
              name="exclusions"
            />
          </div>
        </section>

        <section
          className="scroll-mt-6 border-b border-[var(--line-strong)] py-9"
          id="production"
        >
          <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
            Production
          </p>
          <h2 className="editorial mt-2 text-[32px]">
            What can the team ship in time?
          </h2>
          <div className="mt-7 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {[
              [
                "production_days_min",
                "Fastest turnaround",
                profile.production_days_min,
              ],
              [
                "production_days_max",
                "Normal turnaround",
                profile.production_days_max,
              ],
              ["team_size", "Team size", profile.team_size],
              [
                "research_capacity_hours",
                "Research hours / week",
                profile.research_capacity_hours,
              ],
            ].map(([name, label, value]) => (
              <label className="text-[12px] font-medium" key={String(name)}>
                {String(label)}
                <input
                  className="mt-2 h-11 w-full border border-[var(--line-strong)] px-3 font-normal"
                  defaultValue={Number(value)}
                  min={1}
                  name={String(name)}
                  type="number"
                />
              </label>
            ))}
            <label className="text-[12px] font-medium">
              Editing complexity
              <select
                className="mt-2 h-11 w-full border border-[var(--line-strong)] bg-white px-3 font-normal"
                defaultValue={profile.editing_complexity}
                name="editing_complexity"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
            <label className="text-[12px] font-medium">
              Brand risk
              <select
                className="mt-2 h-11 w-full border border-[var(--line-strong)] bg-white px-3 font-normal"
                defaultValue={profile.risk_tolerance}
                name="risk_tolerance"
              >
                <option value="conservative">Conservative</option>
                <option value="balanced">Balanced</option>
                <option value="experimental">Experimental</option>
              </select>
            </label>
            <label className="text-[12px] font-medium">
              Experiment level
              <select
                className="mt-2 h-11 w-full border border-[var(--line-strong)] bg-white px-3 font-normal"
                defaultValue={profile.experiment_level}
                name="experiment_level"
              >
                <option value="conservative">Conservative</option>
                <option value="balanced">Balanced</option>
                <option value="experimental">Experimental</option>
              </select>
            </label>
            <label className="text-[12px] font-medium">
              Trend share
              <input
                className="mt-2 h-11 w-full border border-[var(--line-strong)] px-3 font-normal"
                defaultValue={profile.evergreen_trend_balance}
                max={1}
                min={0}
                name="evergreen_trend_balance"
                step={0.1}
                type="number"
              />
            </label>
          </div>
        </section>
      </form>

      <section
        className="scroll-mt-6 border-b border-[var(--line-strong)] py-9"
        id="monitored-channels"
      >
        <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
          Monitored channels
        </p>
        <h2 className="editorial mt-2 text-[32px]">
          Which channels represent your niche?
        </h2>
        <p className="mt-3 max-w-[680px] text-[12px] leading-6 text-[var(--muted)]">
          Choose three to five useful peers. They help distinguish real
          cross-channel movement from one creator’s isolated upload.
        </p>
        <p className="mt-2 text-[11px] text-[var(--lime-ink)]">
          {selectedReferences.length} selected
        </p>

        {owned ? (
          <div className="mt-6 flex items-center justify-between gap-4 border-y border-[var(--line)] py-4">
            <div>
              <p className="text-[10px] text-[var(--muted)]">Your channel</p>
              <p className="mt-1 text-[13px] font-semibold">{owned.title}</p>
            </div>
            <span className="inline-flex items-center gap-2 text-[11px] text-[var(--lime-ink)]">
              <Check size={14} /> Connected
            </span>
          </div>
        ) : null}

        <div className="mt-4 divide-y divide-[var(--line)]">
          {references.map((channel) => (
            <label
              className="grid min-h-14 cursor-pointer items-center gap-3 py-4 sm:grid-cols-[32px_1fr_110px_180px]"
              key={channel.channel_id}
            >
              <input
                aria-label={`Monitor ${channel.title}`}
                checked={channel.active}
                className="h-5 w-5 accent-[var(--lime-strong)]"
                disabled={channelToggleMutation.isPending}
                onChange={(event) =>
                  channelToggleMutation.mutate({
                    channelId: channel.channel_id,
                    active: event.target.checked,
                  })
                }
                type="checkbox"
              />
              <p className="text-[12px] font-medium">{channel.title}</p>
              <p
                className={`text-[10px] ${
                  channel.active
                    ? "text-[var(--lime-ink)]"
                    : "text-[var(--muted)]"
                }`}
              >
                {channel.active ? "Selected" : "Paused"}
              </p>
              <p className="text-[10px] text-[var(--muted)]">
                {channel.last_ingested_at
                  ? `Updated ${relativeTime(channel.last_ingested_at)}`
                  : "Waiting for first scan"}
              </p>
            </label>
          ))}
        </div>
        <form
          className="mt-5 grid gap-2 sm:grid-cols-[1fr_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            channelMutation.mutate();
          }}
        >
          <input
            aria-label="YouTube channel ID or channel URL"
            className="h-11 border border-[var(--line-strong)] px-3 text-[12px]"
            onChange={(event) => setChannelInput(event.target.value)}
            placeholder="YouTube channel ID or /channel/ URL"
            value={channelInput}
          />
          <Button
            className="min-h-11"
            disabled={channelMutation.isPending || channelInput.length < 8}
            type="submit"
            variant="primary"
          >
            <Plus size={14} /> Add channel
          </Button>
        </form>
      </section>

      <section
        className="scroll-mt-6 border-b border-[var(--line-strong)] py-9"
        id="notifications"
      >
        <div className="flex items-start gap-3">
          <Bell className="mt-1 text-[var(--lime-strong)]" size={20} />
          <div>
            <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
              Notifications
            </p>
            <h2 className="editorial mt-2 text-[32px]">Useful, not noisy</h2>
            <p className="mt-3 max-w-[680px] text-[12px] leading-6 text-[var(--muted)]">
              In-app digests summarize strong Act opportunities and meaningful
              changes to watched topics. A new evidence video alone does not
              trigger an alert.
            </p>
          </div>
        </div>
        <div className="mt-6 grid gap-5 sm:grid-cols-[240px_1fr_auto]">
          <label className="text-[12px] font-medium">
            Digest cadence
            <select
              className="mt-2 h-11 w-full border border-[var(--line-strong)] bg-white px-3 font-normal"
              onChange={(event) =>
                setCadence(event.target.value as DigestSubscription["cadence"])
              }
              value={cadence}
            >
              <option value="twice_weekly">Twice weekly</option>
              <option value="weekly">Weekly</option>
            </select>
          </label>
          <label className="flex min-h-11 items-center gap-3 self-end text-[12px]">
            <input
              checked={notificationsEnabled}
              className="h-5 w-5 accent-[var(--lime-strong)]"
              onChange={(event) =>
                setNotificationsEnabled(event.target.checked)
              }
              type="checkbox"
            />
            In-app digest enabled
          </label>
          <Button
            className="min-h-11 self-end"
            disabled={notificationMutation.isPending}
            onClick={() => notificationMutation.mutate()}
            variant="primary"
          >
            Save
          </Button>
        </div>
        <p className="mt-4 text-[10px] text-[var(--muted)]">
          Example: 1 opportunity to act on · 2 topics to watch · 12 weak topics
          filtered out. Email delivery is planned after private-beta
          deliverability setup.
        </p>
      </section>

      <section className="scroll-mt-6 py-9" id="connections">
        <div className="flex items-start gap-3">
          <Youtube className="mt-1" size={21} />
          <div>
            <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
              Connections
            </p>
            <h2 className="editorial mt-2 text-[32px]">YouTube Analytics</h2>
            <p className="mt-3 max-w-[680px] text-[12px] leading-6 text-[var(--muted)]">
              Optional read-only access verifies channel fit and measures
              published results. Public monitoring continues if it is not
              connected.
            </p>
          </div>
        </div>

        <div className="mt-6 border border-[var(--line-strong)] p-5">
          {!oauth.feature_enabled ? (
            <p className="text-[12px] text-[var(--muted)]">
              YouTube Analytics is not enabled for this workspace rollout.
            </p>
          ) : !oauth.configured ? (
            <p className="text-[12px] leading-6 text-[var(--muted)]">
              The server needs a Google OAuth client and encryption key before
              this read-only connection can be enabled.
            </p>
          ) : oauth.connected ? (
            <div className="flex flex-wrap items-center justify-between gap-5">
              <div>
                <p className="inline-flex items-center gap-2 text-[12px] font-semibold text-[var(--lime-ink)]">
                  <ShieldCheck size={15} /> Verified connection
                </p>
                <p className="mt-2 text-[10px] text-[var(--muted)]">
                  {oauth.analytics_video_count} videos · last sync{" "}
                  {oauth.last_synced_at
                    ? relativeTime(oauth.last_synced_at)
                    : "pending"}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  disabled={oauthMutation.isPending}
                  onClick={() => oauthMutation.mutate("sync")}
                >
                  <RefreshCw size={13} /> Sync
                </Button>
                <Button
                  disabled={oauthMutation.isPending}
                  onClick={() => oauthMutation.mutate("disconnect")}
                  variant="danger"
                >
                  <Unplug size={13} /> Disconnect
                </Button>
              </div>
            </div>
          ) : (
            <Button
              className="min-h-11"
              disabled={oauthMutation.isPending}
              onClick={() => oauthMutation.mutate("connect")}
              variant="primary"
            >
              <Link2 size={14} /> Connect YouTube read-only
            </Button>
          )}
        </div>

        <details className="group mt-7 border-t border-[var(--line)]">
          <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between text-[12px] font-semibold">
            Technical details
            <span className="text-[10px] font-normal text-[var(--muted)]">
              Profile and delivery versions
            </span>
          </summary>
          <dl className="grid gap-4 pb-6 text-[11px] text-[var(--muted)] sm:grid-cols-3">
            <div>
              <dt>Profile version</dt>
              <dd className="mono mt-1">{profile.profile_version}</dd>
            </div>
            <div>
              <dt>Profile source</dt>
              <dd className="mt-1">{profile.profile_source}</dd>
            </div>
            <div>
              <dt>Digest destination</dt>
              <dd className="mt-1">{subscription.destination}</dd>
            </div>
          </dl>
        </details>
      </section>

      <p aria-live="polite" className="sr-only">
        {profileMutation.isSuccess ? "Channel profile saved." : ""}
        {notificationMutation.isSuccess ? "Notification settings saved." : ""}
      </p>
    </div>
  );
}
