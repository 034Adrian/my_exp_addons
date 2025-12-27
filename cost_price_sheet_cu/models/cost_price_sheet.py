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
    company_id = fields.Many2one
