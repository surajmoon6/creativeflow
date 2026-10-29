export type Status =
  | 'brief_received' | 'in_design' | 'review' | 'revision_requested' | 'approved'
  | 'finalization' | 'payment_pending' | 'paid' | 'delivered' | 'completed'

export interface FileInfo {
  id: number; kind: string; name: string; label: string | null; mime: string; size: number
  width: number | null; height: number | null; created_at: string; downloads?: number
}
export interface ClientRecord {
  id: number; name: string; company: string | null; email: string | null; phone: string | null
  whatsapp: string | null; billing_address: string | null; gstin: string | null; notes: string | null
  display_name: string; created_at: string
  stats?: { total: number; active: number; paid: number; pending_amount: number }
  projects?: ProjectSummary[]
}
export interface ProjectSummary {
  id: number; code: string; name: string; project_type: string; status: Status
  client: { id: number; name: string }; amount: number; total: number; due_date: string | null
  last_activity: string; created_at: string; pending_payment: boolean
}
export interface Comment { id: number; body: string; author: string; status: string; is_extra: boolean; created_at: string }
export interface Version {
  id: number; number: number; deliverable_id: number | null; status: string; note: string | null; created_at: string; pages: number
  comments: Comment[]; master?: FileInfo
}
export type DesignStatus = 'pending' | 'review' | 'changes_requested' | 'approved'
/** One design inside a project (a banner, a standee, a post...). `versions` is ids for the studio, full versions for the client. */
export interface Design<V = number> {
  id: number; title: string; status: DesignStatus; position: number; revisions_used: number
  latest_version_id: number | null; versions: V[]
}
export type AdvanceStatus = 'none' | 'requested' | 'submitted' | 'paid'
export interface ReviewLink {
  id: number; token: string; state: 'active' | 'expired' | 'revoked'; url: string; views: number
  expires_at: string | null; revoked_at: string | null; first_viewed_at: string | null
  last_viewed_at: string | null; created_at: string
}
export interface InvoiceItem { description: string; quantity: number; unit_price: number; amount: number; note: string | null }
export interface Invoice {
  id: number; number: string; subtotal: number; discount: number; tax_rate_bp: number; tax: number
  total: number; status: 'issued' | 'paid' | 'void'; issued_at: string; paid_at: string | null
  advance_paid: number; amount_due: number; notes?: string | null; closing?: string | null
  items: InvoiceItem[]
  bill_to?: { name: string; contact: string; address: string | null; gstin: string | null }
  payment_terms?: string
}
export interface Payment {
  id: number; kind: 'final' | 'advance'; amount: number; reference: string; status: 'submitted' | 'confirmed' | 'rejected'
  provider: string; submitted_at: string; decided_at: string | null; admin_note: string | null
  project?: { id: number; code: string; name: string; client: string }
  invoice_number?: string; proof_file_id?: number | null
}
export interface Activity {
  id: number; actor: string; event: string; message: string; created_at: string
  project?: { id: number; code: string; name: string } | null
}
export interface ShareItem { link: string | null; message: string | null }
export interface ProjectDetail extends Omit<ProjectSummary, 'client'> {
  description: string | null; internal_notes: string | null; width: number | null; height: number | null
  format: string | null; quantity: number; deliverable_types: string | null; discount: number
  gst_enabled: boolean; gst_rate_bp: number; payment_terms: string | null; revisions_included: number
  extra_revision_price: number; revisions_used: number; approved_version_id: number | null
  approved_at: string | null; paid_at: string | null; delivered_at: string | null
  delivery_expires_at: string | null; max_downloads: number | null
  watermark: boolean; preview_rev: number
  advance: { amount: number; paid: number; status: AdvanceStatus; requested_at: string | null; reminded_at: string | null; payments: Payment[] }
  deliverables: Design[]
  client: ClientRecord; versions: Version[]; finals: FileInfo[]; review_links: ReviewLink[]
  active_link: ReviewLink | null; invoice: Invoice | null; payments: Payment[]
  downloads: { id: number; file: string; created_at: string }[]; activity: Activity[]
  share: { review: ShareItem; payment: ShareItem; delivery: ShareItem; advance: ShareItem; whatsapp_number: string | null }
}
export interface Brand { name: string; color: string; email: string; phone: string; whatsapp: string; address: string; gstin: string; has_logo: boolean }
export interface ClientView {
  code: string; name: string; project_type: string; status: Status; client_name: string
  width: number | null; height: number | null; format: string | null; brand: Brand
  revisions_included: number; revisions_used: number; extra_revision_price: number
  watermarked: boolean; preview_rev: number
  deliverables: Design<Version>[]; approved_version_id: number | null
  advance: {
    amount: number; paid: number; due: number; status: AdvanceStatus; upi_id: string | null; payee: string; has_qr: boolean
    pending: Payment | null; last_rejected: Payment | null
  } | null
  approved_at: string | null; link_expires_at: string | null
  invoice: Invoice | null
  payment: {
    upi_id: string | null; payee: string; has_qr: boolean; pending: Payment | null
    last_rejected: Payment | null; confirmed: Payment | null
  } | null
  delivery: { delivered_at: string | null; paid_at: string | null; expires_at: string | null; max_downloads: number | null; files: FileInfo[] } | null
}
export type Settings = Record<string, string | number | boolean | null>

export type QuoteStatus = 'draft' | 'sent' | 'accepted' | 'declined' | 'expired'
export interface QuoteLine { description: string; quantity: number; unit_price: number; amount: number; complimentary: boolean; value: number; detail?: string | null; period?: 'once' | 'monthly'; list_price?: number | null }
export interface QuoteTotals { subtotal: number; discount: number; tax_rate_bp: number; tax: number; total: number; complimentary_value: number; advance: number; recurring: number; one_time: number; savings_monthly: number; savings_once: number }
export interface QuoteDoc {
  number: string; title: string; issued_at: string; valid_until: string
  bill_to: { name: string; contact: string; address: string | null; gstin: string | null }
  items: QuoteLine[]; totals: QuoteTotals; revisions_included: number; advance_percent: number
  notes: string | null; closing: string | null; terms: string | null; brand: Brand
  payment: { upi_id: string; payee: string; uri: string; qr: string } | null
  sections: { title: string; lines: string[]; part?: 'scope' | 'after' | 'appendix'; tone?: 'gain' | 'caution' | 'title' | null }[]; billing: 'once' | 'monthly'; discount_label: string | null
  mode: 'once' | 'monthly' | 'mixed'; scope_first: boolean; recurring_start?: 'now' | 'launch'
}
export interface QuoteSummary {
  id: number; number: string; title: string; status: QuoteStatus; client: { id: number; name: string }
  total: number; valid_until: string; created_at: string; sent_at: string | null; views: number
  last_viewed_at: string | null; responded_at: string | null; project_code: string | null
}
export interface QuoteDetail extends QuoteSummary {
  stored_status: string; document: QuoteDoc; client_id: number; discount: number; gst_enabled: boolean
  gst_rate_bp: number; first_viewed_at: string | null; response_note: string | null
  plan_inclusions: { kind: string; count: number }[]; has_plan: boolean
  project: { id: number; code: string; name: string } | null
  events: { at: string; text: string }[]
  share: { link: string; whatsapp_number: string | null; message: string }
}
export interface ClientQuote {
  document: QuoteDoc; status: QuoteStatus; client_name: string; can_respond: boolean
  responded_at: string | null; response_note: string | null
}

export interface InvoiceDoc {
  number: string; status: Invoice['status']; issued_at: string; paid_at: string | null
  project: { name: string; code: string; project_type: string }
  bill_to: { name: string; contact: string; address: string | null; gstin: string | null }
  items: InvoiceItem[]
  totals: { subtotal: number; discount: number; tax_rate_bp: number; tax: number; total: number; advance_paid: number; amount_due: number }
  notes: string | null; closing: string | null; payment_terms: string | null
  payment: { upi_id: string; payee: string; uri: string; qr: string } | null
  advances: { amount: number; reference: string; received_on: string }[]
  brand: Brand
}
export interface InvoiceDetail extends Invoice {
  document: InvoiceDoc; gst_enabled: boolean; gst_rate_bp: number; link: string | null; editable: boolean
  project: { id: number; code: string; name: string; client: string }
  payments: Payment[]
  advances: { id: number; amount: number; reference: string; note: string | null; received_on: string; proof_file_id: number | null }[]
}

export type PostState = 'planned' | 'brief' | 'review' | 'changes' | 'approved' | 'posted'
export type PostKind = 'post' | 'carousel' | 'reel' | 'story'
export interface Post {
  id: number; title: string; kind: PostKind; state: PostState; status: DesignStatus
  scheduled_at: string | null; platforms: string[]; caption: string | null; media_url: string | null
  posted_at: string | null; latest_version_id: number | null; version_number: number | null; pages: number
  versions: number; revisions_used: number; revisions_included: number; request: string | null
  preview_rev: number; watermarked: boolean; project_id?: number
  brief?: string | null; brief_files?: { id: number; name: string; image: boolean }[]; brief_at?: string | null; brief_by?: string | null; brief_new?: boolean
  unread?: number; fresh?: boolean // messages you haven't opened; a design the client hasn't opened (client side only)
}
export type ThreadItem =
  | { type: 'version'; id: number; at: string; number: number; note: string | null }
  | { type: 'message'; id: number; at: string; mine: boolean; name: string; body: string; changes: boolean }
export interface ClientUpdate { kind: 'creative' | 'message'; post_id: number; title: string; text: string; name?: string | null; at: string; new: boolean }
export interface PlanProgress { kind: PostKind; label: string; included: number; planned: number; approved: number; made: number; posted: number }
export interface CalendarData {
  month: string; client: { id: number; name: string }
  plan: { id: number; name: string; active: boolean; inclusions: { kind: PostKind; count: number }[]; revisions_per_post: number; client_approval: boolean }
  progress: PlanProgress[]; items: Post[]; months: { month: string; count: number }[]; counts: Record<PostState, number>
  brand?: Brand; can_approve?: boolean; me?: { name: string }; updates?: ClientUpdate[]; payment?: PlanDue | null
}
export interface PlanPayStatus { month: string; label: string; due_date: string; opens: string; days_left: number; overdue: boolean; paid: boolean; claimed: boolean; showing: boolean }
export interface PlanDue extends PlanPayStatus { amount: number; upi: { upi_id: string; payee: string; uri: string; qr: string } | null }
export interface PlanDetail {
  client_approval: boolean; payment_reminder: boolean; payment: PlanPayStatus; payment_available: boolean
  payments: { id: number; amount: number; reference: string; note: string | null; received_on: string; proof_file_id: number | null }[]
  id: number; name: string; monthly_price: number; active: boolean; start_date: string | null; invoice: { id: number; number: string } | null
  revisions_per_post: number; inclusions: { kind: PostKind; count: number }[]; project_id: number | null
}
export interface ClientLogin { id: number; name: string; email: string; active: boolean; can_approve: boolean; created_at: string }

export interface Attention { count: number; items: { client_id: number; client: string; post_id: number; title: string; kind: PostKind; scheduled_at: string | null; what: 'brief' | 'message'; count: number; text: string; at: string }[] }
