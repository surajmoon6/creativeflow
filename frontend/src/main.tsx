import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { ToastProvider } from './components/ui'
import './index.css'
import AdminLayout from './layouts/AdminLayout'
import ClientDetail from './pages/admin/ClientDetail'
import Clients from './pages/admin/Clients'
import Dashboard from './pages/admin/Dashboard'
import { ActivityPage, FilesPage, Invoices, Payments } from './pages/admin/Lists'
import Login from './pages/admin/Login'
import ProjectDetail from './pages/admin/ProjectDetail'
import ProjectForm from './pages/admin/ProjectForm'
import Projects from './pages/admin/Projects'
import QuoteDetail from './pages/admin/QuoteDetail'
import InvoiceDetail from './pages/admin/InvoiceDetail'
import Team from './pages/admin/Team'
import Calendar from './pages/admin/Calendar'
import CalendarApp from './pages/portal/CalendarApp'
import QuoteForm from './pages/admin/QuoteForm'
import Quotes from './pages/admin/Quotes'
import Settings from './pages/admin/Settings'
import AdvancePage from './pages/client/Advance'
import Delivery from './pages/client/Delivery'
import InvoicePage from './pages/client/Invoice'
import Portal from './pages/client/Portal'
import QuotePage from './pages/client/QuotePage'
import Review from './pages/client/Review'

function ReviewAlias() {
  const { token } = useParams()
  return <Navigate to={`/r/${token}`} replace />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/r/:token" element={<Portal />}>
            <Route index element={<Review />} />
            <Route path="advance" element={<AdvancePage />} />
            <Route path="invoice" element={<InvoicePage />} />
            <Route path="delivery" element={<Delivery />} />
          </Route>
          <Route path="/review/:token" element={<ReviewAlias />} />
          <Route path="/q/:token" element={<QuotePage />} />
          <Route path="/login" element={<Login />} />
          <Route path="/c" element={<CalendarApp />} />
          <Route element={<AdminLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="projects" element={<Projects />} />
            <Route path="projects/new" element={<ProjectForm />} />
            <Route path="projects/:id" element={<ProjectDetail />} />
            <Route path="projects/:id/edit" element={<ProjectForm />} />
            <Route path="quotes" element={<Quotes />} />
            <Route path="quotes/new" element={<QuoteForm />} />
            <Route path="quotes/:id" element={<QuoteDetail />} />
            <Route path="quotes/:id/edit" element={<QuoteForm />} />
            <Route path="clients" element={<Clients />} />
            <Route path="clients/:id" element={<ClientDetail />} />
            <Route path="invoices" element={<Invoices />} />
            <Route path="invoices/:id" element={<InvoiceDetail />} />
            <Route path="payments" element={<Payments />} />
            <Route path="files" element={<FilesPage />} />
            <Route path="activity" element={<ActivityPage />} />
            <Route path="calendar" element={<Calendar />} />
            <Route path="team" element={<Team />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  </StrictMode>,
)
