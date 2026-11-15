import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { ArrowRight, LoaderCircle } from 'lucide-react';
import s from './ui.module.css';

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className={s.pageHeader}>
      <div>
        {eyebrow && <p className={s.eyebrow}>{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className={s.description}>{description}</p>}
      </div>
      {action}
    </header>
  );
}
export function Button({
  children,
  variant = 'primary',
  busy,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost';
  busy?: boolean;
}) {
  return (
    <button
      {...props}
      className={`${s.button} ${s[variant]} ${props.className ?? ''}`}
      aria-busy={busy}
      disabled={busy || props.disabled}
    >
      {busy && <LoaderCircle size={16} className={s.spin} />}
      {children}
    </button>
  );
}
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`${s.panel} ${className}`}>{children}</section>;
}
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'orange' | 'cyan' | 'teal' | 'purple';
}) {
  return <span className={`${s.badge} ${s[tone]}`}>{children}</span>;
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={s.empty}>
      <div className={s.emptyIcon}>
        <ArrowRight size={22} />
      </div>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
export function Loading({ children = 'Loading data…' }: { children?: ReactNode }) {
  return (
    <div className={s.loading} role="status">
      <LoaderCircle size={20} className={s.spin} />
      {children}
    </div>
  );
}
export function Notice({
  children,
  tone = 'info',
}: {
  children: ReactNode;
  tone?: 'info' | 'warning' | 'error';
}) {
  return (
    <div className={`${s.notice} ${s[tone]}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}
