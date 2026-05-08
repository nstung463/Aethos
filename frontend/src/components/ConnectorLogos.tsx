type LogoProps = {
  className?: string;
};

function baseClassName(className?: string) {
  return className ?? "h-4 w-4";
}

function ImageLogo({ className, src }: LogoProps & { src: string }) {
  return <img src={src} alt="" aria-hidden="true" className={`${baseClassName(className)} object-contain`} />;
}

const CONNECTOR_LOGO_URLS = {
  slack: "https://slack.com/favicon.ico",
  googleDrive: "https://ssl.gstatic.com/docs/doclist/images/drive_2022q3_32dp.png",
  googleDocs: "https://ssl.gstatic.com/docs/documents/images/kix-favicon-2023q4.ico",
  gmail: "https://ssl.gstatic.com/ui/v1/icons/mail/rfr/gmail.ico",
  googleCalendar: "https://calendar.google.com/googlecalendar/images/favicons_2020q4/calendar_31.ico",
  googleSheets: "https://ssl.gstatic.com/docs/spreadsheets/favicon3.ico",
  github: "https://github.githubassets.com/favicons/favicon.svg",
  notion: "https://www.notion.so/images/favicon.ico",
  instagram: "https://www.google.com/s2/favicons?domain=instagram.com&sz=128",
  metaAds: "https://static.xx.fbcdn.net/rsrc.php/y1/r/ay1hV6OlegS.ico",
  browser: "https://www.google.com/chrome/static/images/favicons/favicon-96x96.png",
  linear: "https://linear.app/favicon.ico",
  supabase: "https://supabase.com/favicon/favicon-32x32.png",
  vercel: "https://vercel.com/favicon.ico",
  airtable: "https://airtable.com/favicon.ico",
  outlook: "https://www.google.com/s2/favicons?domain=outlook.live.com&sz=128",
  zapier: "https://cdn.zapier.com/zapier/images/favicon.ico",
  asana: "https://asana.com/favicon.ico",
  monday: "https://cdn.monday.com/images/logos/monday_logo_icon.png",
  make: "https://www.make.com/favicon.ico",
  atlassian: "https://wac-cdn.atlassian.com/assets/img/favicons/atlassian/favicon.png",
  clickUp: "https://clickup.com/favicon.ico",
  neon: "https://www.google.com/s2/favicons?domain=neon.tech&sz=128",
  prisma: "https://www.prisma.io/favicon.ico",
  sentry: "https://www.google.com/s2/favicons?domain=sentry.io&sz=128",
  huggingFace: "https://huggingface.co/favicon.ico",
  hubSpot: "https://www.hubspot.com/hubfs/HubSpot_Logos/HubSpot-Inversed-Favicon.png",
  intercom: "https://www.google.com/s2/favicons?domain=intercom.com&sz=128",
  stripe: "https://stripe.com/favicon.ico",
  paypal: "https://www.paypalobjects.com/webstatic/icon/favicon.ico",
  revenueCat: "https://www.google.com/s2/favicons?domain=revenuecat.com&sz=128",
} as const;

export function SlackLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.slack} />;
}

export function GoogleDriveLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.googleDrive} />;
}

export function GoogleDocsLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.googleDocs} />;
}

export function GmailLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.gmail} />;
}

export function GoogleCalendarLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.googleCalendar} />;
}

export function GoogleSheetsLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.googleSheets} />;
}

export function GitHubLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.github} />;
}

export function NotionLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.notion} />;
}

export function LinearLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.linear} />;
}

export function SupabaseLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.supabase} />;
}

export function VercelLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.vercel} />;
}

export function AirtableLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.airtable} />;
}

export function BrowserLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.browser} />;
}

export function InstagramLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.instagram} />;
}

export function CreatorMarketplaceLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.instagram} />;
}

export function MetaAdsLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.metaAds} />;
}

export function OutlookLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.outlook} />;
}

export function ZapierLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.zapier} />;
}

export function AsanaLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.asana} />;
}

export function MondayLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.monday} />;
}

export function MakeLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.make} />;
}

export function AtlassianLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.atlassian} />;
}

export function ClickUpLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.clickUp} />;
}

export function NeonLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.neon} />;
}

export function PrismaLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.prisma} />;
}

export function SentryLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.sentry} />;
}

export function HuggingFaceLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.huggingFace} />;
}

export function HubSpotLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.hubSpot} />;
}

export function IntercomLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.intercom} />;
}

export function StripeLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.stripe} />;
}

export function PayPalLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.paypal} />;
}

export function RevenueCatLogo({ className }: LogoProps) {
  return <ImageLogo className={className} src={CONNECTOR_LOGO_URLS.revenueCat} />;
}
