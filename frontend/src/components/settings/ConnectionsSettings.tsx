import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Link2,
  LoaderCircle,
  Plus,
  RefreshCcw,
  Search,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ConnectionInfo } from "../../types";
import {
  AirtableLogo,
  AsanaLogo,
  AtlassianLogo,
  BrowserLogo,
  ClickUpLogo,
  CreatorMarketplaceLogo,
  GitHubLogo,
  GmailLogo,
  GoogleCalendarLogo,
  GoogleDriveLogo,
  GoogleSheetsLogo,
  HubSpotLogo,
  HuggingFaceLogo,
  InstagramLogo,
  IntercomLogo,
  LinearLogo,
  MakeLogo,
  MetaAdsLogo,
  MondayLogo,
  NeonLogo,
  NotionLogo,
  OutlookLogo,
  PayPalLogo,
  PrismaLogo,
  RevenueCatLogo,
  SentryLogo,
  SlackLogo,
  SupabaseLogo,
  VercelLogo,
  StripeLogo,
  ZapierLogo,
} from "../ConnectorLogos";
import {
  authorizeConnection,
  deleteConnection,
  fetchConnections,
  fetchConnectionScopes,
  testConnection,
} from "../../utils/extensions";
import { isTrustedConnectionAuthMessage } from "./oauthPopup";

type ConnectorCategory = "recommended" | "communication" | "productivity" | "engineering" | "data";
type ConnectorTab = "apps" | "custom-api" | "custom-mcp";
type ConnectionProvider = "google" | "google-gmail" | "google-drive" | "google-calendar" | "google-sheets" | "slack";
type AuthPhase = "idle" | "starting" | "waiting";
type ConnectorLogoComponent = (props: { className?: string }) => ReactNode;

type ConnectorCatalogItem = {
  id: string;
  provider?: ConnectionProvider;
  nameKey: string;
  nameFallback: string;
  descriptionKey: string;
  descriptionFallback: string;
  badgeKey?: string;
  badgeFallback?: string;
  category: ConnectorCategory;
  accent: string;
  icon: ConnectorLogoComponent;
  connectorTypeKey: string;
  connectorTypeFallback: string;
  authorKey: string;
  authorFallback: string;
  website: string;
  privacyPolicy: string;
  uuid: string;
};

const CONNECTOR_CATALOG: ConnectorCatalogItem[] = [
  {
    id: "instagram",
    nameKey: "connections.catalog.instagram.name",
    nameFallback: "Instagram",
    descriptionKey: "connections.catalog.instagram.description",
    descriptionFallback: "Generate and publish Posts, Stories, or Reels to Instagram.",
    badgeKey: "connections.badges.new",
    badgeFallback: "NEW",
    category: "recommended",
    accent: "from-[#E4405F] to-[#F59E0B]",
    icon: InstagramLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.instagram.com",
    privacyPolicy: "https://privacycenter.instagram.com/policy",
    uuid: "instagram-preview",
  },
  {
    id: "instagram-creator-marketplace",
    nameKey: "connections.catalog.instagramCreatorMarketplace.name",
    nameFallback: "Instagram Creator Marketplace",
    descriptionKey: "connections.catalog.instagramCreatorMarketplace.description",
    descriptionFallback: "Discover creators that fit your brand's reach, topics, and style.",
    badgeKey: "connections.badges.new",
    badgeFallback: "NEW",
    category: "recommended",
    accent: "from-[#7C3AED] to-[#EC4899]",
    icon: CreatorMarketplaceLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://business.instagram.com/creator-marketplace",
    privacyPolicy: "https://privacycenter.instagram.com/policy",
    uuid: "instagram-creator-marketplace-preview",
  },
  {
    id: "meta-ads-manager",
    nameKey: "connections.catalog.metaAdsManager.name",
    nameFallback: "Meta Ads Manager",
    descriptionKey: "connections.catalog.metaAdsManager.description",
    descriptionFallback: "Automate ads insights and optimization to save hours and maximize profits.",
    badgeKey: "connections.badges.new",
    badgeFallback: "NEW",
    category: "recommended",
    accent: "from-[#2563EB] to-[#06B6D4]",
    icon: MetaAdsLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.facebook.com/business/tools/ads-manager",
    privacyPolicy: "https://www.facebook.com/privacy/policy",
    uuid: "meta-ads-manager-preview",
  },
  {
    id: "my-browser",
    nameKey: "connections.catalog.myBrowser.name",
    nameFallback: "My Browser",
    descriptionKey: "connections.catalog.myBrowser.description",
    descriptionFallback: "Access the web on your own browser.",
    badgeKey: "connections.badges.catalog",
    badgeFallback: "Catalog",
    category: "recommended",
    accent: "from-[#111827] to-[#475569]",
    icon: BrowserLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://example.com/browser",
    privacyPolicy: "https://example.com/privacy",
    uuid: "my-browser-preview",
  },
  {
    id: "gmail",
    provider: "google-gmail",
    nameKey: "connections.catalog.gmail.name",
    nameFallback: "Gmail",
    descriptionKey: "connections.catalog.gmail.description",
    descriptionFallback: "Draft replies, search your inbox, and summarize email threads instantly.",
    badgeKey: "connections.badges.live",
    badgeFallback: "Live",
    category: "recommended",
    accent: "from-[#ea4335] via-[#fbbc05] to-[#34a853]",
    icon: GmailLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://mail.google.com",
    privacyPolicy: "https://policies.google.com/privacy",
    uuid: "gmail-google-primary",
  },
  {
    id: "google-drive",
    provider: "google-drive",
    nameKey: "connections.catalog.googleDrive.name",
    nameFallback: "Google Drive",
    descriptionKey: "connections.catalog.googleDrive.description",
    descriptionFallback: "Access docs and files across your workspace in one place.",
    badgeKey: "connections.badges.live",
    badgeFallback: "Live",
    category: "productivity",
    accent: "from-[#0f9d58] via-[#4285f4] to-[#fbbc05]",
    icon: GoogleDriveLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://drive.google.com",
    privacyPolicy: "https://policies.google.com/privacy",
    uuid: "google-drive-primary",
  },
  {
    id: "google-calendar",
    provider: "google-calendar",
    nameKey: "connections.catalog.googleCalendar.name",
    nameFallback: "Google Calendar",
    descriptionKey: "connections.catalog.googleCalendar.description",
    descriptionFallback: "Understand your schedule, manage events, and optimize your time effectively.",
    badgeKey: "connections.badges.live",
    badgeFallback: "Live",
    category: "productivity",
    accent: "from-[#4285f4] to-[#0f9d58]",
    icon: GoogleCalendarLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://calendar.google.com",
    privacyPolicy: "https://policies.google.com/privacy",
    uuid: "google-calendar-primary",
  },
  {
    id: "google-sheets",
    provider: "google-sheets",
    nameKey: "connections.catalog.googleSheets.name",
    nameFallback: "Google Sheets",
    descriptionKey: "connections.catalog.googleSheets.description",
    descriptionFallback: "Read spreadsheet ranges and append structured rows from Aethos.",
    badgeKey: "connections.badges.live",
    badgeFallback: "Live",
    category: "productivity",
    accent: "from-[#0f9d58] via-[#34a853] to-[#fbbc05]",
    icon: GoogleSheetsLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://sheets.google.com",
    privacyPolicy: "https://policies.google.com/privacy",
    uuid: "google-sheets-primary",
  },
  {
    id: "slack",
    provider: "slack",
    nameKey: "connections.catalog.slack.name",
    nameFallback: "Slack",
    descriptionKey: "connections.catalog.slack.description",
    descriptionFallback: "Read and write Slack conversations in Aethos.",
    badgeKey: "connections.badges.live",
    badgeFallback: "Live",
    category: "recommended",
    accent: "from-[#611f69] via-[#36c5f0] to-[#2eb67d]",
    icon: SlackLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://slack.com",
    privacyPolicy: "https://slack.com/privacy-policy",
    uuid: "slack-primary",
  },
  {
    id: "outlook-mail",
    nameKey: "connections.catalog.outlookMail.name",
    nameFallback: "Outlook Mail",
    descriptionKey: "connections.catalog.outlookMail.description",
    descriptionFallback: "Write, search, and manage your Outlook emails seamlessly within Aethos.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "communication",
    accent: "from-[#2563EB] to-[#1D4ED8]",
    icon: OutlookLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://outlook.live.com",
    privacyPolicy: "https://privacy.microsoft.com",
    uuid: "outlook-mail-preview",
  },
  {
    id: "outlook-calendar",
    nameKey: "connections.catalog.outlookCalendar.name",
    nameFallback: "Outlook Calendar",
    descriptionKey: "connections.catalog.outlookCalendar.description",
    descriptionFallback: "Schedule, view, and manage your Outlook events just with a prompt.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "communication",
    accent: "from-[#1D4ED8] to-[#0EA5E9]",
    icon: OutlookLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://outlook.live.com/calendar",
    privacyPolicy: "https://privacy.microsoft.com",
    uuid: "outlook-calendar-preview",
  },
  {
    id: "github",
    nameKey: "connections.catalog.github.name",
    nameFallback: "GitHub",
    descriptionKey: "connections.catalog.github.description",
    descriptionFallback: "Manage repositories, PRs, and engineering workflows.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "engineering",
    accent: "from-[#171515] to-[#444444]",
    icon: GitHubLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://github.com",
    privacyPolicy: "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement",
    uuid: "github-preview",
  },
  {
    id: "notion",
    nameKey: "connections.catalog.notion.name",
    nameFallback: "Notion",
    descriptionKey: "connections.catalog.notion.description",
    descriptionFallback: "Search notes, update docs, and organize internal knowledge.",
    badgeKey: "connections.badges.catalog",
    badgeFallback: "Catalog",
    category: "productivity",
    accent: "from-[#111111] to-[#777777]",
    icon: NotionLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.notion.so",
    privacyPolicy: "https://www.notion.so/product/privacy-policy",
    uuid: "notion-preview",
  },
  {
    id: "zapier",
    nameKey: "connections.catalog.zapier.name",
    nameFallback: "Zapier",
    descriptionKey: "connections.catalog.zapier.description",
    descriptionFallback: "Connect Aethos and automate workflows across thousands of apps.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "productivity",
    accent: "from-[#FF5A1F] to-[#FB923C]",
    icon: ZapierLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://zapier.com",
    privacyPolicy: "https://zapier.com/privacy",
    uuid: "zapier-preview",
  },
  {
    id: "asana",
    nameKey: "connections.catalog.asana.name",
    nameFallback: "Asana",
    descriptionKey: "connections.catalog.asana.description",
    descriptionFallback: "Streamline project and task management with Asana.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "productivity",
    accent: "from-[#FC636B] to-[#F59E0B]",
    icon: AsanaLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://asana.com",
    privacyPolicy: "https://asana.com/terms#privacy-policy",
    uuid: "asana-preview",
  },
  {
    id: "monday",
    nameKey: "connections.catalog.monday.name",
    nameFallback: "monday.com",
    descriptionKey: "connections.catalog.monday.description",
    descriptionFallback: "Coordinate tasks, manage boards, and streamline your project workflows.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "productivity",
    accent: "from-[#F43F5E] to-[#F59E0B]",
    icon: MondayLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://monday.com",
    privacyPolicy: "https://monday.com/privacy/privacy-policy",
    uuid: "monday-preview",
  },
  {
    id: "make",
    nameKey: "connections.catalog.make.name",
    nameFallback: "Make",
    descriptionKey: "connections.catalog.make.description",
    descriptionFallback: "Turn Make workflows into AI tools for intelligent automation execution.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "productivity",
    accent: "from-[#6D28D9] to-[#A855F7]",
    icon: MakeLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.make.com",
    privacyPolicy: "https://www.make.com/en/privacy-notice",
    uuid: "make-preview",
  },
  {
    id: "linear",
    nameKey: "connections.catalog.linear.name",
    nameFallback: "Linear",
    descriptionKey: "connections.catalog.linear.description",
    descriptionFallback: "Track issues, plan milestones, and keep product work in sync.",
    category: "engineering",
    accent: "from-[#5e6ad2] to-[#9aa5ff]",
    icon: LinearLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://linear.app",
    privacyPolicy: "https://linear.app/privacy",
    uuid: "linear-preview",
  },
  {
    id: "atlassian",
    nameKey: "connections.catalog.atlassian.name",
    nameFallback: "Atlassian",
    descriptionKey: "connections.catalog.atlassian.description",
    descriptionFallback: "Search, create, and manage Jira, Confluence, and Compass.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "engineering",
    accent: "from-[#0052CC] to-[#2684FF]",
    icon: AtlassianLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.atlassian.com",
    privacyPolicy: "https://www.atlassian.com/legal/privacy-policy",
    uuid: "atlassian-preview",
  },
  {
    id: "clickup",
    nameKey: "connections.catalog.clickup.name",
    nameFallback: "ClickUp",
    descriptionKey: "connections.catalog.clickup.description",
    descriptionFallback: "Automate task management and project workflows with ClickUp.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "engineering",
    accent: "from-[#7C3AED] to-[#EC4899]",
    icon: ClickUpLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://clickup.com",
    privacyPolicy: "https://clickup.com/privacy",
    uuid: "clickup-preview",
  },
  {
    id: "supabase",
    nameKey: "connections.catalog.supabase.name",
    nameFallback: "Supabase",
    descriptionKey: "connections.catalog.supabase.description",
    descriptionFallback: "Inspect projects, query data, and support product operations.",
    category: "data",
    accent: "from-[#3ecf8e] to-[#0f9d58]",
    icon: SupabaseLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://supabase.com",
    privacyPolicy: "https://supabase.com/privacy",
    uuid: "supabase-preview",
  },
  {
    id: "vercel",
    nameKey: "connections.catalog.vercel.name",
    nameFallback: "Vercel",
    descriptionKey: "connections.catalog.vercel.description",
    descriptionFallback: "Watch deployments, projects, and environments from Aethos.",
    category: "engineering",
    accent: "from-[#111111] to-[#4b5563]",
    icon: VercelLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://vercel.com",
    privacyPolicy: "https://vercel.com/legal/privacy-policy",
    uuid: "vercel-preview",
  },
  {
    id: "neon",
    nameKey: "connections.catalog.neon.name",
    nameFallback: "Neon",
    descriptionKey: "connections.catalog.neon.description",
    descriptionFallback: "Use natural language to query and manage Postgres.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "data",
    accent: "from-[#14B8A6] to-[#22C55E]",
    icon: NeonLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://neon.tech",
    privacyPolicy: "https://neon.tech/privacy-policy",
    uuid: "neon-preview",
  },
  {
    id: "prisma-postgres",
    nameKey: "connections.catalog.prismaPostgres.name",
    nameFallback: "Prisma Postgres",
    descriptionKey: "connections.catalog.prismaPostgres.description",
    descriptionFallback: "Connect to Postgres, manage databases, and query data securely and efficiently.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "data",
    accent: "from-[#0F172A] to-[#334155]",
    icon: PrismaLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.prisma.io/postgres",
    privacyPolicy: "https://www.prisma.io/privacy",
    uuid: "prisma-postgres-preview",
  },
  {
    id: "sentry",
    nameKey: "connections.catalog.sentry.name",
    nameFallback: "Sentry",
    descriptionKey: "connections.catalog.sentry.description",
    descriptionFallback: "Review errors, analyze root causes, and suggest fixes for rapid issue resolution.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "engineering",
    accent: "from-[#111827] to-[#4B5563]",
    icon: SentryLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://sentry.io",
    privacyPolicy: "https://sentry.io/privacy",
    uuid: "sentry-preview",
  },
  {
    id: "hugging-face",
    nameKey: "connections.catalog.huggingFace.name",
    nameFallback: "Hugging Face",
    descriptionKey: "connections.catalog.huggingFace.description",
    descriptionFallback: "Explore AI models, access datasets, and discover the latest research trends.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "data",
    accent: "from-[#F59E0B] to-[#FCD34D]",
    icon: HuggingFaceLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://huggingface.co",
    privacyPolicy: "https://huggingface.co/privacy",
    uuid: "hugging-face-preview",
  },
  {
    id: "hubspot",
    nameKey: "connections.catalog.hubspot.name",
    nameFallback: "HubSpot",
    descriptionKey: "connections.catalog.hubspot.description",
    descriptionFallback: "Search CRM data, track contacts, and analyze sales and marketing insights.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "communication",
    accent: "from-[#F97316] to-[#FB923C]",
    icon: HubSpotLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.hubspot.com",
    privacyPolicy: "https://legal.hubspot.com/privacy-policy",
    uuid: "hubspot-preview",
  },
  {
    id: "intercom",
    nameKey: "connections.catalog.intercom.name",
    nameFallback: "Intercom",
    descriptionKey: "connections.catalog.intercom.description",
    descriptionFallback: "Access customer conversations, analyze feedback, and generate actionable insights.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "communication",
    accent: "from-[#1F8DED] to-[#38BDF8]",
    icon: IntercomLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.intercom.com",
    privacyPolicy: "https://www.intercom.com/legal/privacy",
    uuid: "intercom-preview",
  },
  {
    id: "stripe",
    nameKey: "connections.catalog.stripe.name",
    nameFallback: "Stripe",
    descriptionKey: "connections.catalog.stripe.description",
    descriptionFallback: "Streamline business billing, payments, and account management.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "data",
    accent: "from-[#635BFF] to-[#818CF8]",
    icon: StripeLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://stripe.com",
    privacyPolicy: "https://stripe.com/privacy",
    uuid: "stripe-preview",
  },
  {
    id: "paypal-business",
    nameKey: "connections.catalog.paypalBusiness.name",
    nameFallback: "PayPal for Business",
    descriptionKey: "connections.catalog.paypalBusiness.description",
    descriptionFallback: "Manage transactions, invoices, and business operations efficiently.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "data",
    accent: "from-[#003087] to-[#009CDE]",
    icon: PayPalLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.paypal.com/business",
    privacyPolicy: "https://www.paypal.com/us/legalhub/privacy-full",
    uuid: "paypal-business-preview",
  },
  {
    id: "revenuecat",
    nameKey: "connections.catalog.revenueCat.name",
    nameFallback: "RevenueCat",
    descriptionKey: "connections.catalog.revenueCat.description",
    descriptionFallback: "Manage subscription apps, control entitlements, and automate workflows.",
    badgeKey: "connections.badges.soon",
    badgeFallback: "Soon",
    category: "data",
    accent: "from-[#111827] to-[#6B7280]",
    icon: RevenueCatLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.revenuecat.com",
    privacyPolicy: "https://www.revenuecat.com/privacy",
    uuid: "revenuecat-preview",
  },
  {
    id: "airtable",
    nameKey: "connections.catalog.airtable.name",
    nameFallback: "Airtable",
    descriptionKey: "connections.catalog.airtable.description",
    descriptionFallback: "Work with structured records, ops tables, and team data.",
    category: "data",
    accent: "from-[#fcb400] via-[#ff6b6b] to-[#6c5ce7]",
    icon: AirtableLogo,
    connectorTypeKey: "connections.detail.connectorTypeApp",
    connectorTypeFallback: "App",
    authorKey: "connections.detail.authorAethos",
    authorFallback: "Aethos",
    website: "https://www.airtable.com",
    privacyPolicy: "https://www.airtable.com/company/privacy",
    uuid: "airtable-preview",
  },
];

function formatBadgeTone(connected: boolean, upcoming: boolean) {
  if (connected) return "border-[var(--success)]/25 bg-[var(--success-bg)] text-[var(--success)]";
  if (upcoming) return "border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)]";
  return "border-[var(--accent)]/20 bg-[color:color-mix(in_oklab,var(--accent)_10%,transparent)] text-[var(--accent)]";
}

function formatStatusTone(status: string) {
  return status === "active"
    ? "border-[var(--success)]/25 bg-[var(--success-bg)] text-[var(--success)]"
    : "border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger)]";
}

function connectorIconShell() {
  return "border border-[var(--border-subtle)] bg-[var(--background-menu-white,var(--panel-elevated))] text-[var(--text-primary)] shadow-[0_1px_2px_rgba(0,0,0,0.04)]";
}

function renderCatalogIcon(
  Icon: ConnectorLogoComponent,
  _accent: string,
  className = "h-[18px] w-[18px]",
) {
  return (
    <div className={`flex h-full w-full items-center justify-center rounded-[12px] ${connectorIconShell()}`}>
      <Icon className={className} />
    </div>
  );
}

function providerMatchesConnection(connection: ConnectionInfo, provider?: ConnectionProvider) {
  if (!provider) return false;
  if (connection.provider === provider) return true;
  if (connection.provider === "google" && provider.startsWith("google-")) return true;
  return false;
}

function humanConnectionCount(count: number, singular: string, plural: string) {
  return count === 1 ? singular : plural.replace("{{count}}", String(count));
}

function AddConnectorModal({
  open,
  catalog,
  connections,
  query,
  tab,
  onClose,
  onQueryChange,
  onTabChange,
  onSelect,
  onConnect,
  onDisconnect,
}: {
  open: boolean;
  catalog: ConnectorCatalogItem[];
  connections: ConnectionInfo[];
  query: string;
  tab: ConnectorTab;
  onClose: () => void;
  onQueryChange: (value: string) => void;
  onTabChange: (value: ConnectorTab) => void;
  onSelect: (item: ConnectorCatalogItem) => void;
  onConnect: (item: ConnectorCatalogItem) => void;
  onDisconnect: (connection: ConnectionInfo) => void;
}) {
  const { t } = useTranslation();
  const [selectedItem, setSelectedItem] = useState<ConnectorCatalogItem | null>(null);

  if (!open) return null;

  const recommended = catalog.filter((item) => item.category === "recommended");
  const allApps = catalog.filter((item) => item.category !== "recommended");

  function renderCard(item: ConnectorCatalogItem) {
    const connected = connections.some((connection) => providerMatchesConnection(connection, item.provider));
    const upcoming = !item.provider;
    const Icon = item.icon;
    return (
      <button
        key={item.id}
        type="button"
        onClick={() => {
          setSelectedItem(item);
          onSelect(item);
        }}
        className="flex min-h-[88px] items-center gap-4 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4 text-left transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]"
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border border-[var(--border-subtle)] bg-[var(--surface-soft)]">
          {renderCatalogIcon(Icon, item.accent, "h-6 w-6")}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-[var(--text-primary)]">
              {t(item.nameKey, item.nameFallback)}
            </span>
            {item.badgeKey ? (
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${formatBadgeTone(connected, upcoming)}`}>
                {t(item.badgeKey, item.badgeFallback ?? "")}
              </span>
            ) : null}
          </div>
          <p className="mt-1 line-clamp-2 text-[13px] leading-[18px] text-[var(--text-secondary)]">
            {t(item.descriptionKey, item.descriptionFallback)}
          </p>
        </div>
        {connected ? (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--success-bg)] text-[var(--success)]">
            <Check size={16} strokeWidth={2.2} />
          </div>
        ) : (
          <ChevronRight size={16} className="shrink-0 text-[var(--text-soft)]" strokeWidth={2} />
        )}
      </button>
    );
  }

  if (selectedItem) {
    const Icon = selectedItem.icon;
    const matchedConnection =
      connections.find((connection) => providerMatchesConnection(connection, selectedItem.provider)) ?? null;
    const connected = matchedConnection !== null;
    return (
      <div className="absolute inset-0 z-[100] flex items-center justify-center bg-transparent p-3 backdrop-blur-sm sm:p-4">
        <div className="flex h-full max-h-[calc(100%-1.5rem)] w-full max-w-[760px] flex-col overflow-hidden rounded-[28px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] shadow-2xl">
          <div className="flex items-center justify-between px-6 py-5">
            <div className="basis-0 grow" />
            <button
              type="button"
              onClick={() => setSelectedItem(null)}
              className="inline-flex items-center justify-center rounded-full p-1 text-[var(--text-primary)] transition hover:opacity-80"
              title={t("settings.cancel", "Cancel")}
            >
              <X size={20} strokeWidth={1.9} />
            </button>
          </div>

          <div className="flex flex-col items-center px-6 pb-3">
            <div className="flex w-full max-w-[600px] flex-col items-center gap-8">
              <div className="flex w-full flex-col items-center gap-4 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)]">
                  <div className="h-12 w-12 rounded-[14px]">
                    {renderCatalogIcon(Icon, selectedItem.accent, "h-10 w-10")}
                  </div>
                </div>
                <div className="w-full space-y-2">
                  <div className="flex items-center justify-center gap-2 text-[20px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                    <p>{t(selectedItem.nameKey, selectedItem.nameFallback)}</p>
                  </div>
                  <p className="text-sm leading-6 text-[var(--text-secondary)]">
                    {t(selectedItem.descriptionKey, selectedItem.descriptionFallback)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (!connected) onConnect(selectedItem);
                    }}
                    disabled={connected}
                    className={`inline-flex items-center gap-2 rounded-[10px] px-4 py-2.5 text-sm font-medium transition ${
                      connected
                        ? "cursor-default border border-[var(--border-subtle)] bg-[var(--surface-soft)] text-[var(--text-soft)]"
                        : "bg-[var(--text-primary)] text-[var(--panel-elevated)] hover:opacity-90"
                    }`}
                  >
                    {connected ? <Check size={16} strokeWidth={2.2} /> : <Plus size={16} strokeWidth={2.2} />}
                    {connected
                      ? t("connections.detail.connected", "Connected")
                      : t("connections.detail.connect", "Connect")}
                  </button>
                  {matchedConnection ? (
                    <button
                      type="button"
                      onClick={() => onDisconnect(matchedConnection)}
                      className="inline-flex items-center gap-2 rounded-[10px] border border-[var(--danger-border)] px-4 py-2.5 text-sm font-medium text-[var(--danger)] transition hover:bg-[var(--danger-bg)]"
                    >
                      <Trash2 size={16} strokeWidth={2} />
                      {t("connections.disconnect", "Disconnect")}
                    </button>
                  ) : null}
                </div>
              </div>

              <div className="w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-3">
                <div className="space-y-3 text-sm tracking-[-0.01em]">
                  <div className="flex items-center justify-between gap-4">
                    <div className="text-[var(--text-soft)]">{t("connections.detail.connectorType", "Connector Type")}</div>
                    <div className="text-right text-[var(--text-primary)]">
                      {t(selectedItem.connectorTypeKey, selectedItem.connectorTypeFallback)}
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <div className="text-[var(--text-soft)]">{t("connections.detail.author", "Author")}</div>
                    <div className="text-right text-[var(--text-primary)]">
                      {t(selectedItem.authorKey, selectedItem.authorFallback)}
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <div className="text-[var(--text-soft)]">{t("connections.detail.uuid", "UUID")}</div>
                    <div className="flex items-center gap-2 text-right text-[var(--text-primary)]">
                      <span className="truncate text-xs">{selectedItem.uuid}</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <div className="text-[var(--text-soft)]">{t("connections.detail.website", "Website")}</div>
                    <a
                      href={selectedItem.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[var(--accent)] hover:opacity-80"
                    >
                      <span className="text-xs">{t("connections.detail.openLink", "Open")}</span>
                      <ArrowUpRight size={14} strokeWidth={2} />
                    </a>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <div className="text-[var(--text-soft)]">{t("connections.detail.privacyPolicy", "Privacy Policy")}</div>
                    <a
                      href={selectedItem.privacyPolicy}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[var(--accent)] hover:opacity-80"
                    >
                      <span className="text-xs">{t("connections.detail.openLink", "Open")}</span>
                      <ArrowUpRight size={14} strokeWidth={2} />
                    </a>
                  </div>
                </div>
              </div>

              <div className="w-full pb-6 text-center">
                <a
                  className="text-[13px] text-[var(--text-soft)] underline"
                  href={selectedItem.website}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t("connections.detail.provideFeedback", "Provide feedback")}
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 z-[100] flex items-center justify-center bg-transparent p-3 backdrop-blur-sm sm:p-4">
      <div className="flex h-full max-h-[calc(100%-1.5rem)] w-full max-w-[820px] flex-col overflow-hidden rounded-[28px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] px-6 py-5">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {t("connections.modal.title", "Connectors")}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {t("connections.modal.subtitle", "Connect apps and services Aethos can work with across your workflow.")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            title={t("settings.cancel", "Cancel")}
            className="rounded-xl p-2 text-[var(--text-soft)] transition hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
          >
            <X size={18} strokeWidth={1.9} />
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-6 py-3">
          <div className="flex items-center gap-1 rounded-2xl bg-[var(--surface-soft)] p-1">
            {([
              { id: "apps", label: t("connections.modal.tabs.apps", "Apps") },
              { id: "custom-api", label: t("connections.modal.tabs.customApi", "Custom API") },
              { id: "custom-mcp", label: t("connections.modal.tabs.customMcp", "Custom MCP") },
            ] as Array<{ id: ConnectorTab; label: string }>).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onTabChange(item.id)}
                className={`rounded-xl px-3 py-2 text-sm transition ${
                  tab === item.id
                    ? "bg-[var(--panel-elevated)] text-[var(--text-primary)] shadow-sm"
                    : "text-[var(--text-soft)] hover:text-[var(--text-primary)]"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="relative w-full max-w-[220px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-soft)]" size={15} strokeWidth={1.9} />
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder={t("connections.modal.search", "Search connectors")}
              className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-faint)] focus:border-[var(--border-strong)]"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {tab === "apps" ? (
            <div className="space-y-8">
              {recommended.length > 0 ? (
                <section className="space-y-3">
                  <div className="text-sm text-[var(--text-soft)]">
                    {t("connections.modal.recommended", "Recommended")}
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    {recommended.map(renderCard)}
                  </div>
                </section>
              ) : null}

              <section className="space-y-3">
                <div className="text-sm text-[var(--text-soft)]">
                  {t("connections.modal.apps", "Apps")}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {allApps.map(renderCard)}
                </div>
              </section>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="max-w-md rounded-3xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] p-8 text-center">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--panel-elevated)] text-[var(--accent)]">
                  {tab === "custom-api" ? <Link2 size={22} strokeWidth={1.9} /> : <Sparkles size={22} strokeWidth={1.9} />}
                </div>
                <h3 className="mt-4 text-base font-semibold text-[var(--text-primary)]">
                  {tab === "custom-api"
                    ? t("connections.modal.customApiTitle", "Custom API connectors")
                    : t("connections.modal.customMcpTitle", "Custom MCP connectors")}
                </h3>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  {tab === "custom-api"
                    ? t("connections.modal.customApiDesc", "The UI shell is ready. We can plug custom API connection forms into this space next.")
                    : t("connections.modal.customMcpDesc", "The UI shell is ready. We can plug custom MCP onboarding into this space next.")}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ConnectedAppDetailModal({
  open,
  connection,
  catalogItem,
  connectionScopes,
  onClose,
  onTest,
  onDisconnect,
}: {
  open: boolean;
  connection: ConnectionInfo | null;
  catalogItem: ConnectorCatalogItem | null;
  connectionScopes: string[];
  onClose: () => void;
  onTest: (connection: ConnectionInfo) => void;
  onDisconnect: (connection: ConnectionInfo) => void;
}) {
  const { t } = useTranslation();

  if (!open || !connection) return null;

  const Icon = catalogItem?.icon;

  return (
    <div className="modal-overlay-enter absolute inset-0 z-[100] flex items-center justify-center bg-transparent p-3 backdrop-blur-sm sm:p-4">
      <div className="modal-enter flex h-full max-h-[calc(100%-1.5rem)] w-full max-w-[760px] flex-col overflow-hidden rounded-[28px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-6 py-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-soft)]">
              <div className={`flex h-10 w-10 items-center justify-center rounded-[12px] ${connectorIconShell()}`}>
                {Icon ? <Icon className="h-6 w-6" /> : <Link2 size={18} strokeWidth={1.9} />}
              </div>
            </div>
            <div className="min-w-0">
              <div className="truncate text-base font-semibold text-[var(--text-primary)]">
                {catalogItem ? t(catalogItem.nameKey, catalogItem.nameFallback) : connection.provider}
              </div>
              <div className="mt-0.5 flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--success)]/20 bg-[var(--success-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--success)]">
                  <Check size={12} strokeWidth={2.2} />
                  {t("connections.detail.connected", "Connected")}
                </span>
                <span className="truncate text-xs text-[var(--text-soft)]">{connection.account_label}</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center justify-center rounded-full p-1 text-[var(--text-primary)] transition hover:opacity-80"
            title={t("settings.cancel", "Cancel")}
          >
            <X size={20} strokeWidth={1.9} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto w-full max-w-[640px] space-y-5">
            <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[linear-gradient(180deg,color-mix(in_oklab,var(--accent)_10%,var(--panel-elevated))_0%,var(--panel-elevated)_100%)] p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-soft)]">
                    {t("connections.detail.connectorType", "Connector Type")}
                  </p>
                  <h3 className="text-[22px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                    {catalogItem ? t(catalogItem.nameKey, catalogItem.nameFallback) : connection.provider}
                  </h3>
                  <p className="max-w-[46ch] text-sm leading-6 text-[var(--text-secondary)]">
                    {catalogItem
                      ? t(catalogItem.descriptionKey, catalogItem.descriptionFallback)
                      : t("connections.detail.noDescription", "This connected app is ready to use in Aethos.")}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
                  <button
                    type="button"
                    onClick={() => onTest(connection)}
                    className="inline-flex items-center gap-2 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] px-4 py-2.5 text-sm text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)]"
                  >
                    <CheckCircle2 size={15} strokeWidth={1.8} />
                    {t("connections.testConnection", "Test connection")}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDisconnect(connection)}
                    className="inline-flex items-center gap-2 rounded-[10px] border border-[var(--danger-border)] bg-[var(--panel-elevated)] px-4 py-2.5 text-sm font-medium text-[var(--danger)] transition hover:bg-[var(--danger-bg)]"
                  >
                    <Trash2 size={16} strokeWidth={2} />
                    {t("connections.disconnect", "Disconnect")}
                  </button>
                </div>
              </div>
            </section>

            {connection.last_error ? (
              <div className="flex gap-2 rounded-[20px] border border-[var(--danger-border)] bg-[var(--danger-bg)] p-4 text-sm text-[var(--danger)]">
                <ShieldAlert size={15} strokeWidth={1.8} />
                {connection.last_error}
              </div>
            ) : null}

            <section className="overflow-hidden rounded-[20px] border border-[var(--border-subtle)] bg-[var(--surface-soft)]">
              {[
                [t("connections.detail.connectorType", "Connector Type"), catalogItem ? t(catalogItem.connectorTypeKey, catalogItem.connectorTypeFallback) : t("connections.detail.connectorTypeApp", "App")],
                [
                  t("connections.detail.author", "Author"),
                  catalogItem
                    ? t(catalogItem.authorKey, catalogItem.authorFallback)
                    : t("connections.detail.authorAethos", "Aethos"),
                ],
                [t("connections.detail.uuid", "UUID"), catalogItem?.uuid ?? connection.id],
                [t("connections.detail.account", "Account"), connection.account_label],
                [t("connections.connectionCapabilities", "Capabilities"), connection.capabilities.join(", ") || t("connections.none", "None")],
                [t("connections.connectionScopes", "Scopes"), connectionScopes.join(", ") || t("connections.none", "None")],
              ].map(([label, value], index) => (
                <div
                  key={String(label)}
                  className={`grid gap-1 px-4 py-3 text-left sm:grid-cols-[160px_minmax(0,1fr)] sm:gap-4 ${index > 0 ? "border-t border-[var(--border-subtle)]" : ""}`}
                >
                  <div className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-soft)]">{label}</div>
                  <div className="break-all text-sm text-[var(--text-primary)]">{value}</div>
                </div>
              ))}
            </section>

            {(catalogItem?.website || catalogItem?.privacyPolicy) ? (
              <section className="rounded-[20px] border border-[var(--border-subtle)] bg-[var(--panel-elevated)] p-4">
                <div className="mb-3 text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-soft)]">
                  {t("connections.detail.openLink", "Open")}
                </div>
                <div className="flex flex-wrap gap-2">
                  {catalogItem?.website ? (
                    <a
                      href={catalogItem.website}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-[10px] border border-[var(--border-subtle)] px-4 py-2.5 text-sm text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)]"
                    >
                      <ArrowUpRight size={15} strokeWidth={1.8} />
                      {t("connections.detail.website", "Website")}
                    </a>
                  ) : null}
                  {catalogItem?.privacyPolicy ? (
                    <a
                      href={catalogItem.privacyPolicy}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-[10px] border border-[var(--border-subtle)] px-4 py-2.5 text-sm text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)]"
                    >
                      <ArrowUpRight size={15} strokeWidth={1.8} />
                      {t("connections.detail.privacyPolicy", "Privacy Policy")}
                    </a>
                  ) : null}
                </div>
              </section>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ConnectionsSettings({ rootDir }: { rootDir: string }) {
  const { t } = useTranslation();
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [connectionScopes, setConnectionScopes] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [tab, setTab] = useState<ConnectorTab>("apps");
  const [connectProvider, setConnectProvider] = useState<ConnectionProvider | null>(null);
  const [authPhase, setAuthPhase] = useState<AuthPhase>("idle");
  const authPopupRef = useRef<Window | null>(null);
  const authPopupTimerRef = useRef<number | null>(null);

  async function loadConnections(signal?: AbortSignal) {
    const items = await fetchConnections(rootDir.trim() || undefined, signal);
    setConnections(items);
    setSelectedConnectionId((current) => (
      current && items.some((item) => item.id === current)
        ? current
        : (items[0]?.id || "")
    ));
  }

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setStatus("");
    loadConnections(controller.signal)
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setStatus(err instanceof Error ? err.message : t("connections.loadFailed", "Failed to load connections."));
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedConnection = connections.find((item) => item.id === selectedConnectionId) ?? null;
  const selectedCatalogItem = selectedConnection
    ? (CONNECTOR_CATALOG.find((item) => providerMatchesConnection(selectedConnection, item.provider)) ?? null)
    : null;

  useEffect(() => {
    setConnectionScopes([]);
    if (!selectedConnection) {
      return;
    }
    const controller = new AbortController();
    fetchConnectionScopes(selectedConnection.id, rootDir.trim() || undefined, controller.signal)
      .then(setConnectionScopes)
      .catch(() => setConnectionScopes(selectedConnection.scopes));
    return () => controller.abort();
  }, [rootDir, selectedConnection]);

  useEffect(() => {
    if (detailModalOpen && !selectedConnection) {
      setDetailModalOpen(false);
    }
  }, [detailModalOpen, selectedConnection]);

  useEffect(() => {
    function handleConnectionUpdated(event: MessageEvent) {
      if (!isTrustedConnectionAuthMessage(event, authPopupRef.current, window.location.origin)) return;
      if (authPopupTimerRef.current !== null) {
        window.clearInterval(authPopupTimerRef.current);
        authPopupTimerRef.current = null;
      }
      authPopupRef.current = null;
      setAuthPhase("idle");
      setConnectProvider(null);
      setStatus(t("connections.authCompleted", "Connection completed. The app is now available in Aethos."));
      void loadConnections();
    }
    window.addEventListener("message", handleConnectionUpdated);
    return () => window.removeEventListener("message", handleConnectionUpdated);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (authPopupTimerRef.current !== null) {
        window.clearInterval(authPopupTimerRef.current);
      }
    };
  }, []);

  const filteredCatalog = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return CONNECTOR_CATALOG.filter((item) => {
      if (!normalized) return true;
      return (
        t(item.nameKey, item.nameFallback).toLowerCase().includes(normalized) ||
        t(item.descriptionKey, item.descriptionFallback).toLowerCase().includes(normalized)
      );
    });
  }, [query, t]);

  async function handleAuthorize(provider: ConnectionProvider) {
    setConnectProvider(provider);
    setAuthPhase("starting");
    setStatus(t("connections.connecting", "Connecting..."));
    const popup = window.open("", "_blank");
    if (popup) {
      authPopupRef.current = popup;
    }
    try {
      const payload = await authorizeConnection(
        provider,
        rootDir.trim() || undefined,
        popup ? undefined : window.location.href,
      );
      if (popup && !popup.closed) {
        popup.location.replace(payload.authorization_url);
        popup.focus();
      } else {
        window.location.assign(payload.authorization_url);
      }
      setAuthPhase("waiting");
      setStatus(t("connections.oauthOpened", "OAuth flow opened in a new tab."));
      if (authPopupTimerRef.current !== null) {
        window.clearInterval(authPopupTimerRef.current);
      }
      authPopupTimerRef.current = window.setInterval(() => {
        if (authPopupRef.current && authPopupRef.current.closed) {
          window.clearInterval(authPopupTimerRef.current ?? undefined);
          authPopupTimerRef.current = null;
          authPopupRef.current = null;
          setAuthPhase("idle");
          setConnectProvider(null);
          void loadConnections();
        }
      }, 600);
    } catch (err) {
      if (popup && !popup.closed) {
        popup.close();
      }
      authPopupRef.current = null;
      setConnectProvider(null);
      setAuthPhase("idle");
      setStatus(err instanceof Error ? err.message : t("connections.authorizeFailed", "Failed to start the connection flow."));
    }
  }

  async function handleTestConnection(connection: ConnectionInfo) {
    setStatus(t("connections.testing", "Testing connection..."));
    try {
      const result = await testConnection(connection.id, rootDir.trim() || undefined);
      const label = result.label ? ` ${result.label}` : "";
      setStatus(t("connections.testOk", "Connection is healthy.") + label);
      await loadConnections();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : t("connections.testFailed", "Connection test failed."));
    }
  }

  async function handleDeleteConnection(connection: ConnectionInfo) {
    if (!window.confirm(t("connections.confirmDelete", "Disconnect this account from Aethos?"))) return;
    try {
      await deleteConnection(connection.id, rootDir.trim() || undefined);
      setDetailModalOpen(false);
      await loadConnections();
      setStatus(t("connections.deleted", "Connection removed."));
    } catch (err) {
      setStatus(err instanceof Error ? err.message : t("connections.deleteFailed", "Failed to remove the connection."));
    }
  }

  function handleCatalogConnect(item: ConnectorCatalogItem) {
    if (item.provider) {
      setModalOpen(false);
      void handleAuthorize(item.provider);
      return;
    }
    setStatus(t("connections.comingSoonStatus", "This connector is planned in the UI but not wired yet."));
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-[26px] font-semibold text-[var(--text-primary)]">
          {t("settings.connections", "Connections")}
        </h1>
        <p className="max-w-3xl text-[13px] leading-6 text-[var(--text-secondary)]">
          {t("connections.description", "Connect Aethos to external apps first, then manage extensions separately. This screen is designed as the control center for your app ecosystem.")}
        </p>
      </div>

      {status ? (
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          {status}
        </div>
      ) : null}

      <>
          <section className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-[var(--text-primary)]">
                  {t("connections.connectedApps", "Connected apps")}
                </h2>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  {t("connections.connectedAppsDesc", "Only apps already connected in this project appear here. Use Add connectors to connect a new app.")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void loadConnections()}
                className="inline-flex items-center gap-2 rounded-2xl border border-[var(--border-subtle)] bg-[var(--panel-elevated)] px-4 py-2.5 text-sm text-[var(--text-secondary)] transition hover:bg-[var(--surface-hover)]"
              >
                <RefreshCcw size={16} strokeWidth={1.9} className={isLoading ? "animate-spin" : ""} />
                {t("connections.refresh", "Refresh")}
              </button>
            </div>

            {connections.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-soft)] p-8 text-center">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--panel-elevated)] text-[var(--text-soft)]">
                  <Link2 size={22} strokeWidth={1.9} />
                </div>
                <h3 className="mt-4 text-base font-semibold text-[var(--text-primary)]">
                  {t("connections.emptyTitle", "No connectors yet")}
                </h3>
                <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--text-secondary)]">
                  {t("connections.emptyDesc", "Click Add connectors to browse supported apps and prepare this area for future integrations.")}
                </p>
                <button
                  type="button"
                  onClick={() => setModalOpen(true)}
                  className="mt-5 inline-flex items-center gap-2 rounded-2xl bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
                >
                  <Plus size={16} strokeWidth={2} />
                  {t("connections.addConnectors", "Add connectors")}
                </button>
              </div>
            ) : (
              <div className="grid content-start items-start gap-2 md:grid-cols-2 min-[1180px]:grid-cols-3">
                  <button
                    type="button"
                    onClick={() => setModalOpen(true)}
                    className="group flex min-h-[88px] items-center gap-4 rounded-[12px] border border-dashed border-[var(--accent)]/45 bg-[linear-gradient(180deg,color-mix(in_oklab,var(--accent)_8%,var(--panel-elevated))_0%,var(--panel-elevated)_100%)] p-4 text-left transition hover:border-[var(--accent)] hover:bg-[color:color-mix(in_oklab,var(--accent)_12%,var(--panel-elevated))]"
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-[var(--accent)] text-white shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
                      <Plus size={16} strokeWidth={2.2} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <div className="truncate text-sm font-medium text-[var(--text-primary)]">
                          {t("connections.addConnectors", "Add connectors")}
                        </div>
                        <span className="rounded-full border border-[var(--accent)]/20 bg-[color:color-mix(in_oklab,var(--accent)_10%,transparent)] px-2 py-0.5 text-[10px] font-medium text-[var(--accent)]">
                          {t("connections.badges.catalog", "Catalog")}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-[13px] leading-[18px] text-[var(--text-secondary)]">
                        {t("connections.addConnectorsCardDesc", "Browse supported apps and connect new tools without leaving this settings page.")}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center text-[var(--text-soft)]">
                      <ChevronRight size={16} strokeWidth={2} />
                    </div>
                  </button>
                  {connections.map((connection) => {
                    const card = CONNECTOR_CATALOG.find((item) => providerMatchesConnection(connection, item.provider));
                    const Icon = card?.icon;
                    return (
                      <button
                        key={connection.id}
                        type="button"
                        onClick={() => {
                          setSelectedConnectionId(connection.id);
                          setDetailModalOpen(true);
                        }}
                        className={`flex min-h-[88px] items-center gap-4 rounded-[12px] border p-4 text-left transition ${
                          detailModalOpen && selectedConnectionId === connection.id
                            ? "border-[var(--accent)] bg-[color:color-mix(in_oklab,var(--accent)_10%,var(--panel-elevated))]"
                            : "border-[var(--border-subtle)] bg-[var(--panel-elevated)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]"
                        }`}
                      >
                        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] ${connectorIconShell()}`}>
                          {Icon ? <Icon className="h-5 w-5" /> : <Link2 size={16} strokeWidth={2} />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium text-[var(--text-primary)]">
                                {card ? t(card.nameKey, card.nameFallback) : connection.provider}
                              </div>
                              <div className="mt-1 truncate text-[13px] leading-[18px] text-[var(--text-secondary)]">
                                {card ? t(card.descriptionKey, card.descriptionFallback) : connection.account_label}
                              </div>
                            </div>
                            <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${formatStatusTone(connection.status)}`}>
                              {connection.status}
                            </span>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center text-[var(--text-soft)]">
                          <ChevronRight size={16} strokeWidth={2} />
                        </div>
                      </button>
                    );
                  })}
              </div>
            )}
          </section>
      </>

      {(authPhase !== "idle" && connectProvider) ? (
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          <div className="flex items-center gap-2">
            <LoaderCircle size={16} className="animate-spin" strokeWidth={1.8} />
            {authPhase === "starting"
              ? t("connections.connectingProvider", "Preparing {{provider}} connection...", { provider: connectProvider })
              : t("connections.waitingProvider", "Waiting for {{provider}} authorization to finish...", { provider: connectProvider })}
          </div>
        </div>
      ) : null}

      <AddConnectorModal
        open={modalOpen}
        catalog={filteredCatalog}
        connections={connections}
        query={query}
        tab={tab}
        onClose={() => setModalOpen(false)}
        onQueryChange={setQuery}
        onTabChange={setTab}
        onSelect={() => undefined}
        onConnect={handleCatalogConnect}
        onDisconnect={(connection) => void handleDeleteConnection(connection)}
      />
      <ConnectedAppDetailModal
        open={detailModalOpen}
        connection={selectedConnection}
        catalogItem={selectedCatalogItem}
        connectionScopes={connectionScopes}
        onClose={() => setDetailModalOpen(false)}
        onTest={(connection) => void handleTestConnection(connection)}
        onDisconnect={(connection) => void handleDeleteConnection(connection)}
      />
    </div>
  );
}
