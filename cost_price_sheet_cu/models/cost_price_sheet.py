from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class CostPriceSheet(models.Model):
    _name = "cost.price.sheet"
    _description = "Ficha de costo-Precio (CU)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        index=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("cost.price.sheet"),
    )
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    uom_id = fields.Many2one("uom.uom", string="Ud. de medida", related="product_id.uom_id", readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )

    # Moneda fuente y tipo de cambio por ficha (CUP/MLC)
    source_currency_id = fields.Many2one("res.currency", string="Moneda de costo (fuente)", required=True)
    exchange_rate = fields.Float(
        string="Tipo de cambio aplicado", digits=(16, 6),
        help="Tasa usada para convertir de la moneda fuente a la moneda de la compañía.",
    )
    use_system_rate = fields.Boolean(
        string="Usar tasa del sistema",
        help="Si está activo, se usa la tasa vigente del sistema en la fecha efectiva.",
    )

    # Componentes
    component_ids = fields.One2many("cost.price.component", "sheet_id", string="Componentes")
    material_cost = fields.Monetary(string="Materiales", currency_field="currency_id", compute="_compute_totals", store=True)
    labor_cost = fields.Monetary(string="Mano de obra", currency_field="currency_id", compute="_compute_totals", store=True)
    overhead_cost = fields.Monetary(string="Gastos indirectos", currency_field="currency_id", compute="_compute_totals", store=True)
    other_cost = fields.Monetary(string="Otros", currency_field="currency_id", compute="_compute_totals", store=True)
    total_cost = fields.Monetary(string="Costo total", currency_field="currency_id", compute="_compute_totals", store=True)

    # Márgenes e impuestos
    margin_type = fields.Selection([("percent", "Porcentaje"), ("absolute", "Monto fijo")], default="percent", required=True)
    margin_value = fields.Float(string="Margen", digits=(16, 4), default=0.0)
    tax_ids = fields.Many2many("account.tax", string="Impuestos")

    total_tax = fields.Monetary(string="Impuestos totales", currency_field="currency_id", compute="_compute_price", store=True)
    price_subtotal = fields.Monetary(string="Precio sin impuestos", currency_field="currency_id", compute="_compute_price", store=True)
    price_total = fields.Monetary(string="Precio con impuestos", currency_field="currency_id", compute="_compute_price", store=True)

    quantity = fields.Float(string="Cantidad base", default=1.0)
    unit_price = fields.Monetary(string="Precio unitario", currency_field="currency_id", compute="_compute_price", store=True)

    # Estado y control
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("review", "En revisión"),
            ("approved", "Aprobada"),
            ("archived", "Archivada"),
        ],
        default="draft",
        tracking=True,
    )

    version = fields.Integer(string="Versión", default=1, tracking=True)
    effective_date = fields.Date(string="Fecha efectiva")
    notes = fields.Text(string="Notas/Norma aplicada")

    @api.depends("component_ids.amount_converted", "component_ids.category")
    def _compute_totals(self):
        for rec in self:
            mat = sum(c.amount_converted for c in rec.component_ids if c.category == "material")
            lab = sum(c.amount_converted for c in rec.component_ids if c.category == "labor")
            ovh = sum(c.amount_converted for c in rec.component_ids if c.category == "overhead")
            oth = sum(c.amount_converted for c in rec.component_ids if c.category == "other")
            rec.material_cost = mat
            rec.labor_cost = lab
            rec.overhead_cost = ovh
            rec.other_cost = oth
            rec.total_cost = mat + lab + ovh + oth

    @api.depends("total_cost", "margin_type", "margin_value", "tax_ids", "quantity", "currency_id")
    def _compute_price(self):
        tax_model = self.env["account.tax"]
        for rec in self:
            if rec.margin_type == "absolute":
                subtotal = (rec.total_cost or 0.0) + (rec.margin_value or 0.0)
            else:
                subtotal = (rec.total_cost or 0.0) * (1 + (rec.margin_value or 0.0) / 100.0)

            # compute_all expects price_unit, currency, quantity, product, partner
            taxes_res = rec.tax_ids.compute_all(
                price_unit=subtotal,
                currency=rec.currency_id,
                quantity=rec.quantity or 1.0,
                product=rec.product_id,
                partner=False,
            )
            rec.price_subtotal = taxes_res.get("total_excluded", 0.0)
            rec.total_tax = sum(t.get("amount", 0.0) for t in taxes_res.get("taxes", []))
            rec.price_total = taxes_res.get("total_included", 0.0)
            rec.unit_price = rec.quantity and (rec.price_total / rec.quantity) or 0.0

    def action_submit_review(self):
        self.write({"state": "review"})

    def action_approve(self):
        # Punto de control normativo (rango de margen, categorías obligatorias, etc.)
        self.write({"state": "approved", "effective_date": fields.Date.context_today(self)})

    def action_archive(self):
        self.write({"state": "archived"})

    def convert_amount(self, amount):
        """Convierte usando tasa propia o tasa del sistema en fecha efectiva.
        Devuelve el monto convertido a la moneda de la compañía.
        """
        self.ensure_one()
        date = self.effective_date or fields.Date.context_today(self)
        if self.use_system_rate:
            # usar helper del modelo res.currency
            return self.env["res.currency"]._convert(amount, self.source_currency_id, self.currency_id, self.company_id, date)
        # si no hay tasa de sistema usar exchange_rate multiplicador (por convención: fuente -> compañía)
        rate = self.exchange_rate or 1.0
        return (amount or 0.0) * rate


class CostPriceComponent(models.Model):
    _name = "cost.price.component"
    _description = "Componente de costo (CU)"
    _order = "sequence, id"

    sheet_id = fields.Many2one("cost.price.sheet", required=True, ondelete="cascade")
    name = fields.Char(string="Descripción", required=True)
    category = fields.Selection(
        [
            ("material", "Material"),
            ("labor", "Mano de obra"),
            ("overhead", "Gasto indirecto"),
            ("other", "Otro"),
        ],
        required=True,
    )

    # Monto fuente y conversión
    source_currency_id = fields.Many2one(related="sheet_id.source_currency_id", store=True, readonly=False)
    amount_source = fields.Monetary(string="Monto (moneda fuente)", currency_field="source_currency_id", required=True)
    amount_converted = fields.Monetary(
        string="Monto convertido", currency_field="sheet_id.currency_id", compute="_compute_converted", store=True
    )

    sequence = fields.Integer(default=10)
    account_id = fields.Many2one("account.account", string="Cuenta contable (opcional)")
    partner_id = fields.Many2one("res.partner", string="Proveedor/Trabajador (opcional)")
    purchase_orderline_id = fields.Many2one("purchase.order.line", string="Línea de compra (trazabilidad)")
    stock_move_id = fields.Many2one("stock.move", string="Movimiento de inventario")

    @api.depends("amount_source", "sheet_id.exchange_rate", "sheet_id.use_system_rate", "sheet_id.effective_date")
    def _compute_converted(self):
        for rec in self:
            if not rec.sheet_id:
                rec.amount_converted = 0.0
                continue
            rec.amount_converted = rec.sheet_id.convert_amount(rec.amount_source or 0.0)

    @api.constrains("amount_source")
    def _check_positive(self):
        for rec in self:
            if rec.amount_source is not None and rec.amount_source < 0:
                raise ValidationError(_("El monto fuente no puede ser negativo."))

