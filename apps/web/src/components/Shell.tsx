import { IS_DEMO } from '../lib/env';
import { Suspense, useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  ArrowUpRight,
  BookOpen,
  ChartScatter,
  ChevronRight,
  Files,
  Flame,
  GitCompareArrows,
  LayoutDashboard,
  Menu,
  Orbit,
  Sparkles,
} from 'lucide-react';
import { useWorkspace, WorkspaceBanners } from '../state/WorkspaceProvider';
import { Drawer } from './Drawer';
import { Loading } from './ui';
import s from './Shell.module.css';

const navigation = [
  ['/', 'Обзор', LayoutDashboard],
  ['/investigations', 'Исследования', BookOpen],
  ['/measurements', 'Измерения', ChartScatter],
  ['/compare', 'Сравнение', GitCompareArrows],
  ['/ask', 'Спросить AI', Sparkles],
  ['/missions', 'Сценарии миссий', Orbit],
  ['/reports', 'Отчёты', Files],
] as const;
function Navigation({ onNavigate }: { onNavigate: () => void }) {
  return (
    <nav className={s.nav} aria-label="Разделы Fire Atlas">
      {navigation.map(([path, label, Icon]) => (
        <NavLink
          key={path}
          to={path}
          end={path === '/'}
          onClick={onNavigate}
          className={({ isActive }) => `${s.navItem} ${isActive ? s.active : ''}`}
        >
          <Icon size={19} />
          <span>{label}</span>
          {path === '/ask' && <span className={s.aiBadge}>AI</span>}
        </NavLink>
      ))}
    </nav>
  );
}
function MissionCard({ onNavigate }: { onNavigate: () => void }) {
  const { workspace, config } = useWorkspace();
  return (
    <div className={s.mission}>
      <span className={s.missionIcon}>
        <Orbit size={21} />
      </span>
      <div>
        <small>ТЕКУЩАЯ МИССИЯ</small>
        <strong>{workspace.scenario?.name}</strong>
        <span>
          {config.dictionaries.gravity_regime.find(
            (g) => g.value === workspace.scenario?.gravity_regime,
          )?.label ?? 'Режим не сообщён'}
        </span>
      </div>
      <NavLink to="/missions" onClick={onNavigate} aria-label="Изменить миссию">
        <ChevronRight size={18} />
      </NavLink>
    </div>
  );
}
export function Shell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const previousPath = useRef(location.pathname);
  const main = useRef<HTMLElement | null>(null);
  const { workspace } = useWorkspace();
  const current = navigation.find(([path]) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path),
  );
  useEffect(() => {
    document.title = `${current?.[1] ?? 'Страница не найдена'} · Fire Atlas`;
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      window.scrollTo({ top: 0, left: 0 });
      requestAnimationFrame(() => main.current?.focus({ preventScroll: true }));
    }
  }, [location.pathname]);
  useEffect(() => {
    const media = window.matchMedia('(min-width: 768px)');
    const close = () => {
      if (media.matches) setOpen(false);
    };
    media.addEventListener('change', close);
    return () => media.removeEventListener('change', close);
  }, []);
  return (
    <div className={s.layout}>
      <a className="skipLink" href="#main">
        Перейти к содержимому
      </a>
      <aside className={s.sidebar} aria-label="Главная навигация">
        <NavLink to="/" className={s.brand}>
          <span className={s.logo}>
            <Flame size={26} />
          </span>
          <span>
            Fire Atlas<small>MICROGRAVITY RESEARCH</small>
          </span>
        </NavLink>
        <div className={s.navLabel}>РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <Navigation onNavigate={() => {}} />
        <MissionCard onNavigate={() => {}} />
        <div className={s.sidebarFooter}>
          <span className={s.dot} /> NASA PSI · открытые источники
          <a
            href="https://psi.nasa.gov/physci/repo/"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Открыть репозиторий NASA PSI в новой вкладке"
          >
            <ArrowUpRight size={14} />
          </a>
        </div>
      </aside>
      <div className={s.workspace}>
        <header className={s.topbar}>
          <div className={s.breadcrumb}>
            <button
              className={`${s.mobileMenu} iconButton`}
              onClick={() => setOpen(true)}
              aria-label="Открыть меню"
              aria-expanded={open}
            >
              <Menu size={22} />
            </button>
            <span>Рабочее пространство</span>
            <ChevronRight size={14} />
            <strong>{current?.[1] ?? 'Страница не найдена'}</strong>
          </div>
          <div className={s.topMeta}>
            {IS_DEMO && <span className={s.demoBadge}>ДЕМО</span>}
            <span className={s.revision} title={workspace.data_revision}>
              КОРПУС · {workspace.data_revision.toUpperCase()}
            </span>
            <span className={s.avatar} aria-label="Гостевое пространство">
              Г
            </span>
          </div>
        </header>
        <main ref={main} id="main" className={s.main} tabIndex={-1}>
          <WorkspaceBanners />
          <Suspense fallback={<Loading />}>
            <Outlet />
          </Suspense>
        </main>
        <footer className={s.footer}>
          <span>
            FIRE ATLAS <span className={s.footerDivider}>/</span> FLAME IN FREEFALL
          </span>
          <span>Исследования с проверяемыми основаниями</span>
        </footer>
      </div>
      <Drawer
        open={open}
        onOpenChange={setOpen}
        title="Навигация Fire Atlas"
        description="Выберите раздел рабочего пространства."
      >
        <div className={s.drawerNavigation}>
          <Navigation onNavigate={() => setOpen(false)} />
          <MissionCard onNavigate={() => setOpen(false)} />
        </div>
      </Drawer>
    </div>
  );
}
