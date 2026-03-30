import {
  LayoutDashboard,
  FileText,
  ClipboardList,
  BookTemplate,
  Users,
  Settings,
  LogOut,
  FileUp,
} from 'lucide-react';
import { NavLink } from '@/components/NavLink';
import { useAuthStore } from '@/store/authStore';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarFooter,
  useSidebar,
} from '@/components/ui/sidebar';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';

const mainNav = [
  { title: 'Дашборд', url: '/dashboard', icon: LayoutDashboard },
  { title: 'Мои файлы', url: '/files', icon: FileUp },
  { title: 'Отчёты', url: '/reports', icon: ClipboardList },
  { title: 'Шаблоны', url: '/templates', icon: BookTemplate },
];

const adminNav = [
  { title: 'Все отчёты', url: '/admin/reports', icon: FileText },
  { title: 'Управление шаблонами', url: '/admin/templates', icon: Settings },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === 'collapsed';
  const { user, clearAuth } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  return (
    <Sidebar collapsible="icon" className="border-r-0">
      <div className="flex h-14 items-center gap-2 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent">
          <FileText className="h-4 w-4 text-accent-foreground" />
        </div>
        {!collapsed && (
          <span className="text-sm font-bold tracking-tight text-sidebar-accent-foreground">
            AutoReports
          </span>
        )}
      </div>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-sidebar-foreground/50">Навигация</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNav.map((item) => (
                <SidebarMenuItem key={item.url}>
                  <SidebarMenuButton asChild>
                    <NavLink
                      to={item.url}
                      end={item.url === '/dashboard'}
                      className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                      activeClassName="bg-sidebar-accent text-sidebar-primary font-medium"
                    >
                      <item.icon className="mr-2 h-4 w-4" />
                      {!collapsed && <span>{item.title}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {isAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel className="text-sidebar-foreground/50">
              Администрирование
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {adminNav.map((item) => (
                  <SidebarMenuItem key={item.url}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={item.url}
                        className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                        activeClassName="bg-sidebar-accent text-sidebar-primary font-medium"
                      >
                        <item.icon className="mr-2 h-4 w-4" />
                        {!collapsed && <span>{item.title}</span>}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <SidebarFooter className="p-3">
        {!collapsed && (
          <>
            <Separator className="mb-3 bg-sidebar-border" />
            <div className="flex items-center gap-2 px-1">
              <Users className="h-4 w-4 text-sidebar-foreground/60" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-sidebar-accent-foreground truncate">
                  {user?.username}
                </p>
                <Badge
                  variant="secondary"
                  className="mt-0.5 h-4 text-[10px] bg-sidebar-muted text-sidebar-foreground/70"
                >
                  {user?.role === 'admin' ? 'Администратор' : 'Пользователь'}
                </Badge>
              </div>
            </div>
          </>
        )}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={clearAuth}
              className="text-sidebar-foreground/60 hover:bg-destructive/10 hover:text-destructive"
            >
              <LogOut className="mr-2 h-4 w-4" />
              {!collapsed && <span>Выйти</span>}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
