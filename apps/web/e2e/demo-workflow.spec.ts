import { expect, test } from "@playwright/test";

test("Landing explains the product and carries a channel into signup", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: "Know what to publish before the trend gets obvious.",
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "See a live example" }).click();
  await expect(page).toHaveURL(/#product$/);
  await expect(
    page.getByRole("heading", {
      name: "Free, local and unlimited AI video generation",
    }),
  ).toBeVisible();

  const evidenceHeading = page.getByRole("heading", {
    name: "Not a trend list. A decision system.",
  });
  await expect(evidenceHeading).not.toHaveClass(/is-revealed/);
  await page
    .getByRole("link", { name: "Evidence", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(/#evidence$/);
  await expect(evidenceHeading).toHaveClass(/is-revealed/);

  const channel = page.getByLabel("YouTube channel URL or handle");
  await channel.fill("youtube.com/@creatorlab");
  await page
    .locator('form[action="/register"]')
    .getByRole("button", { name: "Start free" })
    .click();
  await expect(page).toHaveURL(
    /\/register\?channel=youtube.com%2F%40creatorlab$/,
  );
  await expect(
    page.getByRole("heading", { name: "Create your workspace" }),
  ).toBeVisible();
});

test("Mobile Today shows the recommendation before scroll with sticky actions", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/today");

  const firstCard = page.getByTestId("opportunity-card").nth(0);
  const recommendation = firstCard.getByTestId("recommended-video");
  const topic = firstCard.getByTestId("trend-topic");
  const sticky = page.getByTestId("mobile-sticky-actions");
  await expect(recommendation).toBeVisible();
  await expect(topic).toBeVisible();
  await expect(
    sticky.getByRole("button", { name: "Create video plan" }),
  ).toBeVisible();
  await expect(
    sticky.getByRole("button", { name: "Track changes" }),
  ).toBeVisible();
  await expect(
    sticky.getByRole("button", { name: "Dismiss idea" }),
  ).toBeVisible();

  const recommendationBox = await recommendation.boundingBox();
  const stickyBox = await sticky.boundingBox();
  expect(recommendationBox?.y ?? 9999).toBeLessThan(844);
  expect(stickyBox?.y ?? 9999).toBeLessThan(844);
  expect((stickyBox?.y ?? 0) + (stickyBox?.height ?? 9999)).toBeLessThanOrEqual(
    844 - 68,
  );
});

test("Today leads from one recommendation to a video plan", async ({
  page,
}) => {
  await page.goto("/today");
  await expect(
    page.getByRole("heading", { level: 1, name: "Today" }),
  ).toBeVisible();

  const cards = page.getByTestId("opportunity-card");
  const cardCount = await cards.count();
  expect(cardCount).toBeGreaterThan(0);
  expect(cardCount).toBeLessThanOrEqual(3);
  await expect(
    cards.nth(0).getByText("Why now", { exact: true }),
  ).toBeVisible();
  await expect(
    cards.nth(0).getByText("Evidence-backed video opportunity", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(cards.nth(0).getByTestId("insight-status")).toHaveText(
    "Evidence-backed insight",
  );
  await expect(cards.nth(0).getByTestId("insight-statement")).toBeVisible();
  await expect(cards.nth(0)).not.toContainText("What is observably changing");
  await expect(
    cards.nth(0).getByText("Why this channel", { exact: true }),
  ).toBeVisible();
  await expect(cards.nth(0).getByText(/Evidence sources · \d+/)).toBeVisible();
  await expect(cards.nth(0).getByText("Publish by")).toBeVisible();
  await expect(cards.nth(0).getByText("Main risk")).toBeVisible();
  const recommendation = cards.nth(0).getByTestId("recommended-video");
  const topic = cards.nth(0).getByTestId("trend-topic");
  await expect(recommendation).toBeVisible();
  await expect(topic).toBeVisible();
  const hierarchy = await Promise.all([
    recommendation.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).fontSize),
    ),
    topic.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).fontSize),
    ),
  ]);
  expect(hierarchy[0]).toBeGreaterThan(hierarchy[1]);
  await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();

  await cards.nth(0).getByRole("button", { name: "Create video plan" }).click();
  const dialog = page.getByTestId("decision-feedback");
  await expect(
    dialog.getByRole("heading", { name: "Create a video plan" }),
  ).toBeVisible();
  await expect(dialog.getByLabel("Production time")).toBeVisible();
  await expect(dialog.getByLabel("Target publish date")).toBeVisible();
  await dialog.getByRole("button", { name: "Create video plan" }).click();

  await expect(page).toHaveURL(/\/briefs/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Video plans" }),
  ).toBeVisible();
  const brief = page.getByTestId("producer-brief").nth(0);
  await expect(brief.getByText("Core idea")).toBeVisible();
  await expect(brief.getByText("What existing coverage misses")).toBeVisible();
  await expect(brief.getByText("Audience takeaway")).toBeVisible();
  await expect(brief.getByText("Suggested opening")).toBeVisible();
  await expect(brief.getByText("Full video outline")).toBeVisible();
  await expect(brief.getByText("Required proof checklist")).toBeVisible();
  await expect(brief.getByText("Production notes")).toBeVisible();
  await expect(brief.getByText("Claims allowed")).toBeVisible();
  await expect(brief.getByText("23 minutes")).toBeVisible();
  await expect(
    brief.getByTestId("suggested-opening").locator("li"),
  ).toHaveCount(3);
  await expect(
    brief.getByTestId("full-video-outline").locator("li"),
  ).toHaveCount(7);
  await expect(brief.getByTestId("suggested-opening")).toContainText(
    "0:45–1:20",
  );
  await expect(brief.getByTestId("full-video-outline")).toContainText(
    "21:00–23:00",
  );

  await brief.getByRole("button", { name: "Edit plan" }).click();
  const editor = brief.getByTestId("brief-editor");
  await expect(editor.getByLabel("Owner")).toBeVisible();
  await expect(editor.getByLabel("Target publish date")).toBeVisible();
  await expect(editor.getByLabel("Status")).toBeVisible();
  await expect(editor.getByLabel("Audience takeaway")).toBeVisible();
  await editor
    .getByLabel("Working title")
    .fill("Proof-first local video benchmark");
  await editor.getByLabel("Owner").fill("Avery Chen");
  await editor.getByLabel("Status").selectOption("approved");
  await editor.getByLabel("Proof 1 completed").check();
  await editor
    .getByLabel("Production notes")
    .fill("Capture the evaluation setup before recording the result.");
  await editor.getByRole("button", { name: "Save plan" }).click();
  await expect(brief.getByRole("status")).toHaveText("Video plan saved.");
  await expect(
    brief.getByRole("heading", {
      name: "Proof-first local video benchmark",
    }),
  ).toBeVisible();

  const startProduction = brief.getByRole("button", {
    name: "Start production",
  });
  if (await startProduction.isVisible()) {
    await startProduction.click();
  }
  await expect(
    brief.getByText("Production started", { exact: true }),
  ).toBeVisible();
});

test("Mobile brief editor keeps producer controls readable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/briefs");
  const briefs = page.getByTestId("producer-brief");
  await expect(briefs.nth(0)).toBeVisible();
  const briefCount = await briefs.count();
  expect(briefCount).toBeGreaterThan(0);
  const brief = briefs.nth(0);
  const metrics = await brief.evaluate((element) => ({
    scrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    titleSize: Number.parseFloat(
      getComputedStyle(element.querySelector("h2") as HTMLElement).fontSize,
    ),
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
  expect(metrics.titleSize).toBeLessThanOrEqual(34);

  await brief.getByRole("button", { name: "Edit plan" }).click();
  const editor = brief.getByTestId("brief-editor");
  await expect(editor.getByLabel("Working title")).toBeVisible();
  await expect(editor.getByLabel("Target publish date")).toBeVisible();
  await expect(editor.getByLabel("Production notes")).toBeVisible();
  const editorMetrics = await editor.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(editorMetrics.scrollWidth).toBeLessThanOrEqual(
    editorMetrics.viewportWidth,
  );
  await editor.getByRole("button", { name: "Cancel" }).click();
});

test("Idea library is compact and grouped by next step", async ({ page }) => {
  await page.goto("/opportunities");
  await expect(
    page.getByRole("heading", { level: 1, name: "Idea library" }),
  ).toBeVisible();
  for (const group of [
    "Inbox",
    "Tracking",
    "Video plans",
    "Dismissed",
    "Closed",
  ]) {
    await expect(
      page
        .getByRole("navigation", { name: "Opportunity status groups" })
        .getByRole("link", { name: new RegExp(group) }),
    ).toBeVisible();
  }
  const columns = page.getByTestId("opportunity-library-columns");
  for (const column of [
    "Idea",
    "Next step",
    "Stage",
    "Publish by",
    "Fit",
    "Status",
  ]) {
    await expect(columns.getByText(column, { exact: true })).toBeVisible();
  }
  await expect(page.getByTestId("opportunity-card")).toHaveCount(0);
  expect(
    await page.getByTestId("opportunity-library-row").count(),
  ).toBeGreaterThan(0);

  await page.getByRole("link", { name: /Tracking/ }).click();
  await expect(page).toHaveURL(/\/opportunities\?group=watching$/);
  await expect(
    page.getByRole("heading", { level: 2, name: "Tracking", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/sources and metrics update/).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: /Inbox/ }).click();
  await expect(page).toHaveURL(/\/opportunities\?group=needs_decision$/);
});

test("Track and Dismiss capture a condition and can replace a prior decision", async ({
  page,
}) => {
  await page.goto("/opportunities");
  await expect(
    page.getByRole("heading", { level: 1, name: "Idea library" }),
  ).toBeVisible();
  const rows = page.getByTestId("opportunity-library-row");
  expect(await rows.count()).toBeGreaterThan(0);
  await rows.nth(0).click();
  const card = page.getByTestId("opportunity-card");

  await card.getByRole("button", { name: "Track changes" }).click();
  await page
    .getByTestId("decision-feedback")
    .getByRole("button", { name: "More independent evidence" })
    .click();
  await page
    .getByTestId("decision-feedback")
    .getByRole("button", { name: "Save Track changes" })
    .click();
  await expect(card.locator('[role="status"]:visible')).toHaveText(
    "Tracking changes for this idea.",
  );

  await card.getByRole("button", { name: "Dismiss idea" }).click();
  await page
    .getByTestId("decision-feedback")
    .getByRole("button", { name: "Not relevant" })
    .click();
  await page
    .getByTestId("decision-feedback")
    .getByRole("button", { name: "Save Dismiss idea" })
    .click();
  await expect(card.locator('[role="status"]:visible')).toHaveText(
    "Idea removed from the active library.",
  );
});

test("Opportunity library opens full evidence through detail", async ({
  page,
}) => {
  await page.goto("/opportunities");
  await page.getByTestId("opportunity-library-row").nth(0).click();
  await expect(page).toHaveURL(
    /\/opportunities\/[a-f0-9-]+\?from=(needs_decision|watching|in_production|skipped|expired)$/,
  );
  const sourceGroup = new URL(page.url()).searchParams.get("from");
  expect(sourceGroup).toBeTruthy();
  await page.getByRole("tab", { name: "Sources" }).click();

  await expect(page).toHaveURL(
    new RegExp(
      `/opportunities/[a-f0-9-]+\\?from=${sourceGroup}&section=evidence$`,
    ),
  );
  await expect(page.getByRole("tab", { name: "Sources" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByText("Technical details")).toBeVisible();
  await expect(page.getByText("Score components")).not.toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Evidence behind the recommendation",
    }),
  ).toBeVisible();
  await expect(page.getByText("Key evidence only")).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 3, name: "Drivers" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 3, name: "Amplifiers" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 3, name: "Supporting evidence" }),
  ).toBeVisible();
  const keySources = page.getByTestId("evidence-source");
  expect(await keySources.count()).toBeGreaterThanOrEqual(3);
  expect(await keySources.count()).toBeLessThanOrEqual(5);
  await expect(keySources.nth(0).getByText("Outlier")).toBeVisible();
  await expect(keySources.nth(0).getByText("Transcript")).toBeVisible();
  await expect(keySources.nth(0).getByText("Angle contribution")).toBeVisible();
  await page.getByRole("button", { name: "Show all" }).click();
  await expect(page.getByText("All stored evidence")).toBeVisible();
  await expect(page.getByTestId("evidence-source")).toHaveCount(12);
  await page.getByRole("button", { name: "Show key evidence" }).click();
  await expect(page.getByTestId("evidence-source")).toHaveCount(5);

  await page.getByRole("tab", { name: "Overview" }).click();
  await expect(page).toHaveURL(
    new RegExp(`/opportunities/[a-f0-9-]+\\?from=${sourceGroup}$`),
  );
  await page.getByTestId("gap-analysis").locator("summary").click();
  const primaryGap = page.getByTestId("primary-content-gap");
  await expect(
    primaryGap.getByText("Evidence-backed content gap"),
  ).toBeVisible();
  await expect(primaryGap.getByTestId("content-gap-insight")).toBeVisible();
  for (const field of [
    "Why it is open",
    "Audience",
    "Promise",
    "Required proof",
    "Production effort",
    "What current videos cover",
    "What current videos miss",
    "Evidence strength",
    "Source links",
  ]) {
    await expect(primaryGap.getByText(field, { exact: true })).toBeVisible();
  }
  const sourceLinks = primaryGap.locator('a[target="_blank"]');
  expect(await sourceLinks.count()).toBeGreaterThan(0);
  const coverageMap = page.getByTestId("coverage-map");
  for (const stage of [
    "Well covered",
    "Under-covered",
    "Unanswered audience demand",
    "Recommended open angle",
  ]) {
    await expect(coverageMap.getByText(stage, { exact: true })).toBeVisible();
  }
  await expect(page.getByTestId("alternative-gap")).toHaveCount(2);

  await page.getByText("Technical details", { exact: true }).click();
  await expect(page.getByText("Score components")).toBeVisible();
});

test("Onboarding needs only a YouTube channel", async ({ page }) => {
  await page.goto("/onboarding");
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Paste your YouTube channel. We’ll do the rest.",
    }),
  ).toBeVisible();
  await expect(page.getByText("Channel connected")).toBeVisible();
  await expect(page.getByText("Atlas Labs")).toBeVisible();
  const analyzeButton = page.getByRole("button", {
    name: "Re-analyze channel",
  });
  const analyzeColors = await analyzeButton.evaluate((element) => {
    const styles = getComputedStyle(element);
    return {
      background: styles.backgroundColor,
      foreground: styles.color,
    };
  });
  expect(analyzeColors.foreground).toBe("rgb(255, 255, 255)");
  expect(analyzeColors.background).not.toBe(analyzeColors.foreground);
  const openToday = page.getByRole("link", { name: "Open Today" });
  const openTodayColors = await openToday.evaluate((element) => {
    const styles = getComputedStyle(element);
    return {
      background: styles.backgroundColor,
      foreground: styles.color,
    };
  });
  expect(openTodayColors.foreground).toBe("rgb(255, 255, 255)");
  expect(openTodayColors.background).not.toBe(openTodayColors.foreground);
});

test("Video plan sharing and Performance use non-causal language", async ({
  page,
}) => {
  await page.goto("/briefs");
  const brief = page.getByTestId("producer-brief").nth(0);
  await brief.getByRole("button", { name: "Copy plan" }).click();
  await expect(brief.getByRole("button", { name: "Copied" })).toBeVisible();
  await brief.getByRole("button", { name: "Share link" }).click();
  await expect(
    brief.getByRole("button", { name: "Link copied" }),
  ).toBeVisible();

  await page.goto("/results");
  await expect(
    page.getByRole("heading", { level: 1, name: "Performance" }),
  ).toBeVisible();
  await expect(
    page.locator("header").filter({
      has: page.getByRole("heading", { level: 1, name: "Performance" }),
    }),
  ).toContainText("compares its early performance with your channel baseline");
  const comparators = page.getByTestId("result-comparator");
  await expect(comparators.nth(0)).toBeVisible();
  const comparatorCount = await comparators.count();
  expect(comparatorCount).toBeGreaterThan(0);
  const comparator = comparators.nth(0);
  await expect(comparator.getByText("24h views")).toBeVisible();
  await expect(comparator.getByText("284K")).toBeVisible();
  await expect(
    comparator.getByText("Comparable median", { exact: true }),
  ).toBeVisible();
  await expect(comparator.getByText("142K")).toBeVisible();
  await expect(comparator.getByText("Compared with")).toBeVisible();
  await expect(
    comparator.getByText("8 similar long-form videos"),
  ).toBeVisible();
  await expect(
    comparator.getByText("Published during the last 6 months"),
  ).toBeVisible();
  await expect(
    comparator.getByText("Similar duration and topic family"),
  ).toBeVisible();
  await expect(comparator.getByTestId("associated-difference")).toHaveText(
    "+100% associated difference",
  );
  await expect(
    comparator.getByText(/Association does not prove causation/),
  ).toBeVisible();
  await expect(page.getByText(/EarlySignal increased/)).toHaveCount(0);
  const detailButtons = page.getByRole("button", {
    name: "View performance details",
  });
  const detailButtonCount = await detailButtons.count();
  expect(detailButtonCount).toBeGreaterThan(0);
  await detailButtons.nth(0).click();
  await expect(page.getByTestId("result-details").nth(0)).toContainText(
    "Baseline definition",
  );
});

test("Performance suppresses percentage for a small comparator sample", async ({
  page,
}) => {
  await page.route("**/api/v1/workspaces/*/outcomes", async (route) => {
    await route.fulfill({
      json: [
        {
          id: "early-outcome",
          workspace_id: "bc31e161-f438-58aa-84a9-5cfdb6fc358a",
          signal_id: "b917fb6b-c02c-55ee-8291-0e672034bcb5",
          content_brief_id: null,
          youtube_video_id: "earlyresult01",
          published_at: "2026-07-29T12:00:00Z",
          baseline_definition:
            "Median performance of three comparable long-form uploads.",
          performance_json: {
            version: "outcome-metrics-v2",
            interpretation: "associated_uplift_not_causal",
            views_24h: 73_000,
            baseline_views_24h: 65_000,
            channel_relative_uplift_24h: 1.123,
            comparator: {
              version: "outcome-metrics-v2",
              sample_size: 3,
              sample_size_24h: 3,
              minimum_stable_sample_size: 5,
              stability: "early",
              stability_24h: "early",
              views_24h: 65_000,
              filters: {
                content_type: "long",
                duration_ratio: "0.6–1.6x",
                topic_family: "title-token similarity ranked",
                upload_period_days: 180,
                sponsored: false,
              },
            },
          },
          success_status: "successful",
          user_notes: "The first complete analytics snapshot is available.",
          link_status: "active",
          association_version: "outcome-association-v1",
          metrics_version: "outcome-metrics-v2",
          created_at: "2026-07-30T12:00:00Z",
          updated_at: "2026-07-30T12:00:00Z",
        },
      ],
    });
  });

  await page.goto("/results");
  const earlyComparator = page.getByTestId("early-comparator");
  await expect(earlyComparator).toBeVisible();
  await expect(
    earlyComparator.getByText(
      "Not enough comparable videos for a stable uplift estimate",
    ),
  ).toBeVisible();
  await expect(
    earlyComparator.getByText(
      "3 available; at least 5 are required before showing a percentage.",
    ),
  ).toBeVisible();
  await expect(page.getByText("3 similar long-form videos")).toBeVisible();
  await expect(page.getByTestId("associated-difference")).toHaveCount(0);
  await expect(page.getByText("+12%")).toHaveCount(0);
  await expect(page.getByText("early", { exact: true })).toBeVisible();
});

test("Mobile Performance keeps the comparator readable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/results");
  const comparators = page.getByTestId("result-comparator");
  await expect(comparators.nth(0)).toBeVisible();
  const comparatorCount = await comparators.count();
  expect(comparatorCount).toBeGreaterThan(0);
  const comparator = comparators.nth(0);
  const metrics = await comparator.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth);
  await expect(comparator.getByText("24h views")).toBeVisible();
  await expect(
    comparator.getByText("Comparable median", { exact: true }),
  ).toBeVisible();
  await expect(comparator.getByText("Compared with")).toBeVisible();
});

test("Initial and empty states explain what happens next", async ({ page }) => {
  await page.route("**/api/v1/workspaces/*/digest/latest", async (route) => {
    await route.fulfill({
      json: {
        id: "empty-digest",
        workspace_id: "bc31e161-f438-58aa-84a9-5cfdb6fc358a",
        period_start: "2026-07-28T00:00:00Z",
        period_end: "2026-07-29T00:00:00Z",
        status: "delivered",
        content: {
          version: "test",
          workspace_name: "Atlas Labs",
          source_mode: "demo",
          items: [],
        },
        generated_at: "2026-07-28T12:00:00Z",
        delivered_at: "2026-07-28T12:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/workspaces/*/signals", async (route) => {
    await route.fulfill({
      json: {
        items: [],
        total: 0,
        data_freshness: "2026-07-28T12:00:00Z",
        data_mode: "demo",
        available_modes: ["demo"],
      },
    });
  });
  await page.goto("/today");
  await expect(page.getByText("Building your first signal set")).toBeVisible();
  await expect(
    page.getByText(/first relevant candidates will appear here automatically/),
  ).toBeVisible();

  await page.goto("/opportunities");
  await expect(
    page.getByText("Nothing in inbox", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/waiting for your choice/).first()).toBeVisible();

  await page.unrouteAll();
  await page.route("**/api/v1/workspaces/*/outcomes", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(
    "**/api/v1/workspaces/*/outcomes/suggestions?status=suggested",
    async (route) => {
      await route.fulfill({ json: [] });
    },
  );
  await page.goto("/results");
  await expect(
    page.getByText("No published plan to measure yet"),
  ).toBeVisible();
  await expect(
    page.getByText(/Move a video plan into production/),
  ).toBeVisible();
});

test("Mobile opportunity keeps decision actions in reach", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/opportunities");
  const mobileRow = page.getByTestId("opportunity-library-row").nth(0);
  const mobileLibraryMetrics = await mobileRow.evaluate((element) => ({
    pageScrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    rowHeight: element.getBoundingClientRect().height,
  }));
  expect(mobileLibraryMetrics.pageScrollWidth).toBeLessThanOrEqual(
    mobileLibraryMetrics.viewportWidth,
  );
  expect(mobileLibraryMetrics.rowHeight).toBeLessThan(220);
  await mobileRow.click();
  await page.getByRole("tab", { name: "Overview" }).click();

  const sticky = page.getByTestId("mobile-sticky-actions");
  const stickyAct = sticky.getByRole("button", {
    name: "Create video plan",
  });
  const stickyWatch = sticky.getByRole("button", {
    name: "Track changes",
  });
  const stickySkip = sticky.getByRole("button", {
    name: "Dismiss idea",
  });
  await expect(stickyAct).toBeVisible();
  await expect(stickyWatch).toBeVisible();
  await expect(stickySkip).toBeVisible();
  const actBox = await stickyAct.boundingBox();
  expect(actBox?.y ?? 9999).toBeLessThan(844);

  await page.getByRole("tab", { name: "Sources" }).click();
  await expect(page.getByText("Key evidence only")).toBeVisible();
  await expect(page.getByTestId("evidence-source")).toHaveCount(5);
  const mobileEvidenceMetrics = await page
    .getByTestId("evidence-source")
    .nth(0)
    .evaluate((element) => ({
      pageScrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      rowHeight: element.getBoundingClientRect().height,
    }));
  expect(mobileEvidenceMetrics.pageScrollWidth).toBeLessThanOrEqual(
    mobileEvidenceMetrics.viewportWidth,
  );
  expect(mobileEvidenceMetrics.rowHeight).toBeLessThan(280);

  await page.getByRole("tab", { name: "Overview" }).click();
  await page.getByText("See how this differs from existing coverage").click();
  await expect(page.getByTestId("alternative-gap")).toHaveCount(2);
  const mobileGapMetrics = await page
    .getByTestId("primary-content-gap")
    .evaluate((element) => ({
      pageScrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      titleSize: Number.parseFloat(
        getComputedStyle(element.querySelector("h2") as HTMLElement).fontSize,
      ),
    }));
  expect(mobileGapMetrics.pageScrollWidth).toBeLessThanOrEqual(
    mobileGapMetrics.viewportWidth,
  );
  expect(mobileGapMetrics.titleSize).toBeLessThanOrEqual(34);
});

test("Content gap can be opened through a stable deep link", async ({
  page,
}) => {
  await page.goto(
    "/opportunities/1d1033ea-b6e6-5282-a63c-f24e4a161411?section=content-gap",
  );
  await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByTestId("gap-analysis")).toHaveAttribute("open", "");
  await expect(page.getByTestId("primary-content-gap")).toBeVisible();
});

test("Opportunity tabs and legacy links preserve browser history", async ({
  page,
}) => {
  const signalId = "1d1033ea-b6e6-5282-a63c-f24e4a161411";
  await page.goto(`/signals/${signalId}?from=needs_decision&section=evidence`);
  await expect(page).toHaveURL(
    `/opportunities/${signalId}?from=needs_decision&section=evidence`,
  );
  await expect(page.getByRole("tab", { name: "Sources" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.getByRole("tab", { name: "Timing" }).click();
  await expect(page).toHaveURL(
    `/opportunities/${signalId}?from=needs_decision&section=lifecycle`,
  );
  await page.goBack();
  await expect(page).toHaveURL(
    `/opportunities/${signalId}?from=needs_decision&section=evidence`,
  );
  await expect(page.getByRole("tab", { name: "Sources" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.getByRole("link", { name: "All ideas" }).click();
  await expect(page).toHaveURL("/opportunities?group=needs_decision");
  await expect(page.getByRole("link", { name: /Inbox/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
});
