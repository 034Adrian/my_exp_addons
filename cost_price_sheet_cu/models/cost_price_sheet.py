from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class CostPriceSheet(models.Model):
    _name = "cost.price.sheet"
    _description = "Ficha de costo-Precio (CU)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="Referencia", requiered=True, index=True, copy=False,
                       default=lambda self: self.env["ir.sequence"].next_by_code("cost.price.sheet"))
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    uom_id = fields.Many2one("uom.uom", string="Ud. de medida", related="product_id.uom_id", readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currencyid = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currencyid)

    # Moneda fuente y tipo de cambio por ficha (CUP/MLC)
    sourcecurrencyid = fields.Many2one("res.currency", string="Moneda de costo (fuente)", required=True)
    exchange_rate = fields.Float(
        string="Tipo de cambio aplicado", digits=(16, 6),
        help="Tasa usada para convertir de la moneda fuente a la moneda de la compañía."
    )
    usesystemrate = fields.Boolean(
        string="Usar tasa del sistema",
        help="Si está activo, se usa la tasa vigente del sistema en la fecha efectiva."
    )

    # Componentes
    componentids = fields.One2many("cost.price.component", "sheetid", string="Componentes")
    materialcost = fields.Monetary(string="Materiales", currencyfield="currencyid", compute="compute_totals", store=True)
    laborcost = fields.Monetary(string="Mano de obra", currencyfield="currencyid", compute="compute_totals", store=True)
    overheadcost = fields.Monetary(string="Gastos indirectos", currencyfield="currencyid", compute="compute_totals", store=True)
    othercost = fields.Monetary(string="Otros", currencyfield="currencyid", compute="compute_totals", store=True)
    totalcost = fields.Monetary(string="Costo total", currencyfield="currencyid", compute="compute_totals", store=True)

    # Márgenes e impuestos
    margin_type = fields.Selection([("percent", "Porcentaje"), ("absolute", "Monto fijo")], default="percent", required=True)
    margin_value = fields.Float(string="Margen", digits=(16, 4), default=0.0)
    tax_ids = fields.Many2many("account.tax", string="Impuestos")

    totaltax = fields.Monetary(string="Impuestos totales", currencyfield="currencyid", compute="compute_price", store=True)
    pricesubtotal = fields.Monetary(string="Precio sin impuestos", currencyfield="currencyid", compute="compute_price", store=True)
    pricetotal = fields.Monetary(string="Precio con impuestos", currencyfield="currencyid", compute="compute_price", store=True)

    quantity = fields.Float(string="Cantidad base", default=1.0)
    unitprice = fields.Monetary(string="Precio unitario", currencyfield="currencyid", compute="compute_price", store=True)

    # Estado y control
    state = fields.Selection([
        ("draft", "Borrador"),
        ("review", "En revisión"),
        ("approved", "Aprobada"),
        ("archived", "Archivada"),
    ], default="draft", tracking=True)

    version = fields.Integer(string="Versión", default=1, tracking=True)
    effective_date = fields.Date(string="Fecha efectiva")
    notes = fields.Text(string="Notas/Norma aplicada")

    @api.depends("componentids.amountconverted", "component_ids.category")
    def computetotals(self):
        for rec in self:
            mat = sum(c.amountconverted for c in rec.componentids if c.category == "material")
            lab = sum(c.amountconverted for c in rec.componentids if c.category == "labor")
            ovh = sum(c.amountconverted for c in rec.componentids if c.category == "overhead")
            oth = sum(c.amountconverted for c in rec.componentids if c.category == "other")
            rec.material_cost = mat
            rec.labor_cost = lab
            rec.overhead_cost = ovh
            rec.other_cost = oth
            rec.total_cost = mat + lab + ovh + oth

    @api.depends("totalcost", "margintype", "marginvalue", "taxids", "quantity", "currency_id")
    def computeprice(self):
        for rec in self:
            subtotal = rec.totalcost + (rec.marginvalue or 0.0) if rec.margin_type == "absolute" \
                else rec.totalcost * (1 + (rec.marginvalue or 0.0) / 100.0)

            taxesres = rec.taxids.compute_all(
                price_unit=subtotal,
                currency=rec.currency_id,
                quantity=rec.quantity,
                product=rec.product_id,
                partner=False  # puedes enlazar un partner específico si aplica
            )
            rec.pricesubtotal = taxesres["total_excluded"]
            rec.totaltax = sum(t.get("amount", 0.0) for t in taxesres.get("taxes", []))
            rec.pricetotal = taxesres["total_included"]
            rec.unitprice = rec.quantity and (rec.pricetotal / rec.quantity) or 0.0

    def actionsubmitreview(self):
        self.write({"state": "review"})

    def action_approve(self):
        # Punto de control normativo (rango de margen, categorías obligatorias, etc.)
        self.write({"state": "approved", "effective_date": fields.Date.today()})

    def action_archive(self):
        self.write({"state": "archived"})

    def convertamount(self, amount):
        "Convierte usando tasa propia o tasa del sistema en fecha efectiva."
        self.ensure_one()
        if self.usesystemrate:
            date = self.effectivedate or fields.Date.contexttoday(self)
            return self.sourcecurrencyid._convert(
                from_amount=amount,
                tocurrency=self.currencyid,
                company=self.company_id,
                date=date
            )
        rate = self.exchange_rate or 1.0
        return amount * rate


class CostPriceComponent(models.Model):
    _name = "cost.price.component"
    _description = "Componente de costo (CU)"
    _order = "sequence, id"

    sheet_id = fields.Many2one("cost.price.sheet", required=True, ondelete="cascade")
    name = fields.Char(string="Descripción", required=True)
    category = fields.Selection([
        ("material", "Material"),
        ("labor", "Mano de obra"),
        ("overhead", "Gasto indirecto"),
        ("other", "Otro"),
    ], required=True)

    # Monto fuente y conversión
    sourcecurrencyid = fields.Many2one(related="sheetid.sourcecurrency_id", store=True)
    amountsource = fields.Monetary(string="Monto (moneda fuente)", currencyfield="sourcecurrencyid", required=True)
    amount_converted = fields.Monetary(
        string="Monto convertido", currencyfield="sheetid.currency_id",
        compute="computeconverted", store=True
    )

    sequence = fields.Integer(default=10)
    account_id = fields.Many2one("account.account", string="Cuenta contable (opcional)")
    partner_id = fields.Many2one("res.partner", string="Proveedor/Trabajador (opcional)")
    purchaseorderline_id = fields.Many2one("purchase.order.line", string="Línea de compra (trazabilidad)")
    stockmoveid = fields.Many2one("stock.move", string="Movimiento de inventario")

    @api.depends("amountsource", "sheetid.exchangerate", "sheetid.usesystemrate", "sheetid.effectivedate")
    def computeconverted(self):
        for rec in self:
            rec.amountconverted = rec.sheetid.convertamount(rec.amount_source or 0.0)

    @api.constrains("amount_source")
    def checkpositive(self):
        for rec in self:
            if rec.amount_source < 0:
                raise ValidationError(_("El monto fuente no puede ser negativo."))

