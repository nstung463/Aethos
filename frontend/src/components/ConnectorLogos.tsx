type LogoProps = {
  className?: string;
};

function baseClassName(className?: string) {
  return className ?? "h-4 w-4";
}

function MonogramLogo({
  className,
  label,
  fill,
  textColor = "#FFFFFF",
}: LogoProps & { label: string; fill: string; textColor?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <rect x="3" y="3" width="18" height="18" rx="5" fill={fill} />
      <text
        x="12"
        y="12.5"
        fill={textColor}
        fontSize="6.5"
        fontWeight="700"
        textAnchor="middle"
        dominantBaseline="middle"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
      >
        {label}
      </text>
    </svg>
  );
}

export function SlackLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <rect x="10.25" y="1.75" width="3.5" height="8" rx="1.75" fill="#36C5F0" />
      <rect x="14.25" y="10.25" width="8" height="3.5" rx="1.75" fill="#2EB67D" />
      <rect x="10.25" y="14.25" width="3.5" height="8" rx="1.75" fill="#ECB22E" />
      <rect x="1.75" y="10.25" width="8" height="3.5" rx="1.75" fill="#E01E5A" />
    </svg>
  );
}

export function GoogleDriveLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path d="M9 3h6l6 10h-6L9 3Z" fill="#0F9D58" />
      <path d="M9 3 3 13h6l6-10H9Z" fill="#4285F4" />
      <path d="M3 13 9 23h12l-6-10H3Z" fill="#F4B400" />
    </svg>
  );
}

export function GoogleDocsLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path d="M7 2.5h7.5L19 7v14a.5.5 0 0 1-.5.5h-11A2.5 2.5 0 0 1 5 19V5a2.5 2.5 0 0 1 2-2.45Z" fill="#4285F4" />
      <path d="M14.5 2.5V7H19l-4.5-4.5Z" fill="#AECBFA" />
      <rect x="8" y="10" width="8" height="1.5" rx=".75" fill="#E8F0FE" />
      <rect x="8" y="13" width="8" height="1.5" rx=".75" fill="#E8F0FE" />
      <rect x="8" y="16" width="6" height="1.5" rx=".75" fill="#E8F0FE" />
    </svg>
  );
}

export function GmailLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path d="M4.75 7.25A2.25 2.25 0 0 1 7 5h10a2.25 2.25 0 0 1 2.25 2.25v9.5A2.25 2.25 0 0 1 17 19H7a2.25 2.25 0 0 1-2.25-2.25v-9.5Z" fill="#FFFFFF" />
      <path d="M6.35 8.1 12 12.25 17.65 8.1" fill="none" stroke="#EA4335" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 17.4V8.85L12 13.2l6-4.35v8.55" fill="none" stroke="#34A853" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.1 8.3 4.9 7.25A2.2 2.2 0 0 1 7 5h1.1l3.9 2.9L15.9 5H17a2.2 2.2 0 0 1 2.1 2.25l-1.2 1.05L12 4.1 6.1 8.3Z" fill="#FBBC04" />
      <path d="M4.75 7.25v9.5A2.25 2.25 0 0 0 7 19h1.2V9.55L4.75 7.25Z" fill="#34A853" />
      <path d="M19.25 7.25v9.5A2.25 2.25 0 0 1 17 19h-1.2V9.55l3.45-2.3Z" fill="#4285F4" />
    </svg>
  );
}

export function GoogleCalendarLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <rect x="4" y="5" width="16" height="15" rx="3" fill="#4285F4" />
      <rect x="4" y="8" width="16" height="3.5" fill="#1A73E8" />
      <rect x="7" y="2.5" width="2" height="4" rx="1" fill="#34A853" />
      <rect x="15" y="2.5" width="2" height="4" rx="1" fill="#34A853" />
      <path d="M12 17.2c-2 0-3.4-1.2-3.4-2.95 0-1.83 1.53-3.08 3.63-3.08 1 0 1.9.24 2.54.7l-.7 1.3a3.15 3.15 0 0 0-1.72-.48c-.95 0-1.58.56-1.58 1.42 0 .84.63 1.4 1.56 1.4.78 0 1.31-.3 1.7-.94h-1.83v-1.2h3.64c.03.18.05.39.05.62 0 1.92-1.34 3.21-3.9 3.21Z" fill="#fff" />
    </svg>
  );
}

export function GoogleSheetsLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path d="M7 2.5h7.5L19 7v14a.5.5 0 0 1-.5.5h-11A2.5 2.5 0 0 1 5 19V5a2.5 2.5 0 0 1 2-2.45Z" fill="#0F9D58" />
      <path d="M14.5 2.5V7H19l-4.5-4.5Z" fill="#A8DAB5" />
      <rect x="8" y="10" width="8" height="7" rx="1" fill="#E6F4EA" />
      <path d="M10.6 10v7M13.4 10v7M8 12.3h8M8 14.7h8" stroke="#0F9D58" strokeWidth="1" />
    </svg>
  );
}

export function GitHubLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path
        d="M12 3.2a8.8 8.8 0 0 0-2.78 17.15c.44.08.6-.19.6-.42v-1.48c-2.45.54-2.97-1.04-2.97-1.04-.4-1.03-.98-1.31-.98-1.31-.8-.55.06-.54.06-.54.88.06 1.35.91 1.35.91.79 1.33 2.06.95 2.56.73.08-.57.31-.95.56-1.17-1.95-.22-4-.98-4-4.37 0-.96.34-1.74.9-2.36-.1-.22-.4-1.12.08-2.34 0 0 .73-.24 2.4.9a8.3 8.3 0 0 1 4.36 0c1.67-1.14 2.4-.9 2.4-.9.48 1.22.18 2.12.09 2.34.56.62.9 1.4.9 2.36 0 3.4-2.05 4.15-4 4.37.31.27.59.81.59 1.64v2.43c0 .24.16.51.6.42A8.8 8.8 0 0 0 12 3.2Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function NotionLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <rect x="4" y="4" width="16" height="16" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 17V8.2l1.15-.08 4.7 6.28V8h2.15v8.8l-1.1.08-4.76-6.35V17H8Z" fill="currentColor" />
    </svg>
  );
}

export function LinearLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <defs>
        <linearGradient id="linear-logo-gradient" x1="4" y1="4" x2="20" y2="20" gradientUnits="userSpaceOnUse">
          <stop stopColor="#5E6AD2" />
          <stop offset="1" stopColor="#9AA5FF" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="8" fill="url(#linear-logo-gradient)" />
      <path d="M9 8.5h6v2H9Zm0 5h6v2H9Z" fill="#fff" />
    </svg>
  );
}

export function SupabaseLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path d="M13.2 4.2c.36-.47 1.1-.22 1.1.38V14.6c0 .2-.06.4-.18.56l-3.9 5.35c-.36.48-1.12.23-1.12-.37V10.17c0-.2.06-.4.18-.56l3.94-5.4Z" fill="#3ECF8E" />
      <path d="M14.82 4.6v9.98c0 .2-.06.4-.18.56l-3.9 5.35c-.3.4-.9.28-1.03-.16l5.1-15.73Z" fill="#2FBF71" />
    </svg>
  );
}

export function VercelLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path d="M12 4 20 18H4L12 4Z" fill="currentColor" />
    </svg>
  );
}

export function AirtableLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={baseClassName(className)}>
      <path d="M4 8.2 11.4 4a1.2 1.2 0 0 1 1.2 0L20 8.2c.53.3.5 1.08-.05 1.33l-7.24 3.4a1.7 1.7 0 0 1-1.44 0L4.05 9.55C3.5 9.29 3.47 8.5 4 8.2Z" fill="#FCB400" />
      <path d="M11 14.2v5.1c0 .6-.63 1-1.17.74l-4.65-2.2A1.3 1.3 0 0 1 4.4 16.7v-4.48c0-.48.5-.8.94-.59l4.88 2.3c.48.23.78.72.78 1.27Z" fill="#18BFFF" />
      <path d="m19.65 11.7-5 2.36c-.45.22-.73.67-.73 1.17v4.18c0 .63.67 1.03 1.22.72l4.24-2.4c.39-.22.62-.62.62-1.06v-4.38c0-.47-.48-.79-.9-.59Z" fill="#F82B60" />
    </svg>
  );
}

export function BrowserLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="WB" fill="#111827" />;
}

export function InstagramLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="IG" fill="#E4405F" />;
}

export function CreatorMarketplaceLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="CM" fill="#7C3AED" />;
}

export function MetaAdsLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="MA" fill="#2563EB" />;
}

export function OutlookLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="O" fill="#2563EB" />;
}

export function ZapierLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="Z" fill="#FF5A1F" />;
}

export function AsanaLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="A" fill="#FC636B" />;
}

export function MondayLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="M" fill="#F43F5E" />;
}

export function MakeLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="MK" fill="#6D28D9" />;
}

export function AtlassianLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="AT" fill="#0052CC" />;
}

export function ClickUpLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="CU" fill="#7C3AED" />;
}

export function NeonLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="N" fill="#14B8A6" />;
}

export function PrismaLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="P" fill="#0F172A" />;
}

export function SentryLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="S" fill="#111827" />;
}

export function HuggingFaceLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="HF" fill="#F59E0B" textColor="#1F2937" />;
}

export function HubSpotLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="HS" fill="#F97316" />;
}

export function IntercomLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="IC" fill="#1F8DED" />;
}

export function StripeLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="ST" fill="#635BFF" />;
}

export function PayPalLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="PP" fill="#003087" />;
}

export function RevenueCatLogo(props: LogoProps) {
  return <MonogramLogo {...props} label="RC" fill="#111827" />;
}
