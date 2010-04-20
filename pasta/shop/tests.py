from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

#from pasta.contact.models import Contact
from pasta import pasta_settings
from pasta.product.models import TaxClass, Product
from pasta.shop.models import Contact, Order


class OrderTest(TestCase):
    def setUp(self):
        pasta_settings.PASTA_PRICE_INCLUDES_TAX = True

    def create_contact(self):
        return Contact.objects.create(
            billing_first_name=u'Hans',
            billing_last_name=u'Muster',
            shipping_same_as_billing=True,
            )

    def create_order(self, contact=None):
        contact = contact or self.create_contact()

        return Order.objects.create(
            contact=contact,
            currency='CHF',
            )

    def create_tax_classes(self):
        tax_class, created = TaxClass.objects.get_or_create(
            name='Standard Swiss Tax Rate',
            rate=Decimal('7.60'),
            )

        tax_class_germany, created = TaxClass.objects.get_or_create(
            name='Umsatzsteuer (Germany)',
            rate=Decimal('19.00'),
            )

        tax_class_something, created = TaxClass.objects.get_or_create(
            name='Some tax rate',
            rate=Decimal('12.50'),
            )

        return tax_class, tax_class_germany, tax_class_something


    def create_product(self):
        tax_class, tax_class_germany, tax_class_something = self.create_tax_classes()

        product = Product.objects.create(
            name='Test Product 1',
            )

        # An old price in CHF which should not influence the rest of the tests
        product.prices.create(
            currency='CHF',
            tax_class=tax_class,
            _unit_price=Decimal('99.90'),
            tax_included=True
            )

        product.prices.create(
            currency='CHF',
            tax_class=tax_class,
            _unit_price=Decimal('79.90'),
            tax_included=True,
            )

        product.prices.create(
            currency='EUR',
            tax_class=tax_class_germany,
            _unit_price=Decimal('49.90'),
            tax_included=True,
            )

        product.prices.create(
            currency='ASDF',
            tax_class=tax_class_something,
            _unit_price=Decimal('65.00'),
            tax_included=False,
            )

        return product

    def test_01_basic_order(self):
        product = self.create_product()
        order = self.create_order()

        self.assertEqual(product.get_price(order.currency).currency, order.currency)

        order.modify(product, 5)
        order.modify(product, -4)
        item = order.modify(product, 1)

        self.assertEqual(order.items.count(), 1)

        self.assertEqual(item.quantity, 2)

        item_price = Decimal('79.90')
        line_item_price = item_price * item.quantity
        order_total = Decimal('159.80')
        tax_factor = Decimal('1.076')

        self.assertAlmostEqual(order.items_subtotal, order_total / tax_factor)
        self.assertAlmostEqual(order.items_subtotal + order.items_tax, order_total)
        self.assertAlmostEqual(order.total, order_total)

        self.assertAlmostEqual(item._unit_price, item_price / tax_factor)
        self.assertAlmostEqual(item.total, line_item_price)


        self.assertAlmostEqual(item.unit_price, item_price)
        self.assertAlmostEqual(item.line_item_price, line_item_price)
        self.assertAlmostEqual(item.line_item_discount, 0)
        self.assertAlmostEqual(item.discounted_line_item_price, line_item_price)
        self.assertAlmostEqual(item.total, line_item_price)

        # Switch around tax handling and re-test
        pasta_settings.PASTA_PRICE_INCLUDES_TAX = False

        self.assertAlmostEqual(item.unit_price, item_price / tax_factor)
        self.assertAlmostEqual(item.line_item_price, line_item_price / tax_factor)
        self.assertAlmostEqual(item.line_item_discount, 0 / tax_factor)
        self.assertAlmostEqual(item.discounted_line_item_price, line_item_price / tax_factor)
        self.assertAlmostEqual(item.total, line_item_price) # NOT divided with tax_factor!

        # Switch tax handling back
        pasta_settings.PASTA_PRICE_INCLUDES_TAX = True

    def test_02_eur_order(self):
        product = self.create_product()
        order = self.create_order()

        order.currency = 'EUR'
        order.save()

        item = order.modify(product, 2)

        self.assertEqual(item.unit_price, Decimal('49.90'))
        self.assertEqual(item.currency, order.currency)

    def test_03_mixed_currencies(self):
        """
        Create an invalid order
        """

        p1 = self.create_product()
        p2 = self.create_product()
        order = self.create_order()

        order.currency = 'CHF'
        i1 = order.modify(p1, 3)

        order.currency = 'EUR'
        self.assertRaises(ValidationError, lambda: order.modify(p2, 2))

        # Validation should still fail
        self.assertRaises(ValidationError, lambda: order.validate())

        order.currency = 'CHF'
        # Order should validate now
        order.validate()