import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { ArrowUpRight, BookOpen, ChartScatter, ChevronRight, Files, Flame, GitCompareArrows, LayoutDashboard, Menu, Orbit, Sparkles, X } from 'lucide-react';
import s from './Shell.module.css';
import { useWorkspace, WorkspaceBanners } from '../state/WorkspaceProvider';

const navigation = [
  ['/', 'Обзор', LayoutDashboard], ['/investigations', 'Исследования', BookOpen],
  ['/measurements', 'Измерения', ChartScatter], ['/compare', 'Сравнение', GitCompareArrows],
  ['/ask', 'Спросить AI', Sparkles], ['/missions', 'Сценарии миссий', Orbit], ['/reports', 'Отчёты', Files],
] as const;

export function Shell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const { workspace } = useWorkspace();
  const current = navigation.find(([path]) => path === '/' ? location.pathname === '/' : location.pathname.startsWith(path));
  return <div className={s.layout}>
    <a className="skipLink" href="#main">Перейти к содержимому</a>
    {open && <button className={s.backdrop} aria-label="Закрыть навигацию" onClick={() => setOpen(false)} />}
    <aside className={`${s.sidebar} ${open ? s.open : ''}`} aria-label="Главная навигация">
      <NavLink to="/" className={s.brand} onClick={() => setOpen(false)}><span className={s.logo}><Flame size={26} /></span><span>Fire Atlas<small>MICROGRAVITY RESEARCH</small></span></NavLink>
      <button className={`${s.mobileClose} iconButton`} aria-label="Закрыть меню" onClick={() => setOpen(false)}><X /></button>
      <div className={s.navLabel}>РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav className={s.nav}>{navigation.map(([path, label, Icon]) => <NavLink key={path} to={path} end={path === '/'} onClick={() => setOpen(false)} className={({ isActive }) => `${s.navItem} ${isActive ? s.active : ''}`}><Icon size={19} /><span>{label}</span>{path === '/ask' && <span className={s.aiBadge}>AI</span>}</NavLink>)}</nav>
      <div className={s.mission}><span className={s.missionIcon}><Orbit size={21} /></span><div><small>ТЕКУЩАЯ МИССИЯ</small><strong>{workspace.scenario.name}</strong><span>{workspace.scenario.gravity_regime === 'microgravity' ? 'Микрогравитация' : 'Частичная гравитация'}</span></div><NavLink to="/missions" aria-label="Изменить миссию"><ChevronRight size={18} /></NavLink></div>
      <div className={s.sidebarFooter}><span className={s.dot} /> NASA PSI · открытые источники<a href="https://psi.nasa.gov/physci/repo/" target="_blank" rel="noreferrer" aria-label="Открыть репозиторий NASA PSI в новой вкладке"><ArrowUpRight size={14} /></a></div>
    </aside>
    <div className={s.workspace}>
      <header className={s.topbar}><div className={s.breadcrumb}><button className={`${s.mobileMenu} iconButton`} onClick={() => setOpen(true)} aria-label="Открыть меню" aria-expanded={open}><Menu size={22} /></button><span>Рабочее пространство</span><ChevronRight size={14} /><strong>{current?.[1] ?? 'Исследование'}</strong></div><div className={s.topMeta}>{import.meta.env.VITE_USE_MOCKS === 'true' && <span className={s.demoBadge}>ДЕМО</span>}<span className={s.revision} title={workspace.data_revision}>КОРПУС · {workspace.data_revision.toUpperCase()}</span><span className={s.avatar} aria-label="Гостевое пространство">Г</span></div></header>
      <main id="main" className={s.main}><WorkspaceBanners /><Outlet /></main>
      <footer className={s.footer}><span>FIRE ATLAS <span className={s.footerDivider}>/</span> FLAME IN FREEFALL</span><span>Исследования с проверяемыми основаниями</span></footer>
    </div>
  </div>;
}
