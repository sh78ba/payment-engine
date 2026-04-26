"""
Management command to seed the database with test merchants, bank accounts,
and credit history.

Creates 3 merchants with realistic credit histories to demonstrate the
payout engine functionality.

Usage:
    python manage.py seed_merchants
    python manage.py seed_merchants --flush  # Clear existing data first
"""

import uuid
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from payouts.models import Merchant, BankAccount, LedgerEntry


class Command(BaseCommand):
    help = "Seed the database with test merchants and credit history"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing data before seeding",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("Flushing existing data...")
            LedgerEntry.objects.all().delete()
            BankAccount.objects.all().delete()
            Merchant.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Data flushed."))

        # Check if merchants already exist
        if Merchant.objects.exists():
            self.stdout.write(
                self.style.WARNING("Merchants already exist. Use --flush to re-seed.")
            )
            return

        now = timezone.now()

        # ── Merchant 1: Arjun's Design Studio ──────────────────────────
        m1 = Merchant.objects.create(
            name="Arjun's Design Studio",
            email="arjun@designstudio.in",
        )
        BankAccount.objects.create(
            merchant=m1,
            account_number="1234567890123456",
            ifsc_code="HDFC0001234",
            account_holder_name="Arjun Mehta",
            bank_name="HDFC Bank",
        )
        # Credit history: 5 payments totaling ₹1,50,000 (1,50,00,000 paise)
        credits_m1 = [
            (5000000, "Payment from Acme Corp - Website Design", 30),
            (3500000, "Payment from GlobalTech - UI/UX Package", 25),
            (2000000, "Payment from StartupXYZ - Logo Design", 15),
            (2500000, "Payment from MediaFlow - Brand Identity", 7),
            (2000000, "Payment from TechNova - Landing Page", 2),
        ]
        for amount, desc, days_ago in credits_m1:
            LedgerEntry.objects.create(
                merchant=m1,
                entry_type=LedgerEntry.EntryType.CREDIT,
                amount_paise=amount,
                description=desc,
                created_at=now - timedelta(days=days_ago),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"  Created merchant: {m1.name} (₹1,50,000 in credits)"
            )
        )

        # ── Merchant 2: Priya's Content Agency ─────────────────────────
        m2 = Merchant.objects.create(
            name="Priya's Content Agency",
            email="priya@contentagency.in",
        )
        ba2 = BankAccount.objects.create(
            merchant=m2,
            account_number="9876543210987654",
            ifsc_code="ICIC0005678",
            account_holder_name="Priya Sharma",
            bank_name="ICICI Bank",
        )
        # Credit history: 4 payments totaling ₹85,000
        credits_m2 = [
            (2500000, "Payment from BlogCorp - Content Package", 20),
            (1500000, "Payment from EduPlatform - Course Content", 14),
            (3000000, "Payment from NewsDaily - Article Series", 8),
            (1500000, "Payment from SaaSCo - Documentation", 3),
        ]
        for amount, desc, days_ago in credits_m2:
            LedgerEntry.objects.create(
                merchant=m2,
                entry_type=LedgerEntry.EntryType.CREDIT,
                amount_paise=amount,
                description=desc,
                created_at=now - timedelta(days=days_ago),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"  Created merchant: {m2.name} (₹85,000 in credits)"
            )
        )

        # ── Merchant 3: Rahul's Dev Shop ───────────────────────────────
        m3 = Merchant.objects.create(
            name="Rahul's Dev Shop",
            email="rahul@devshop.in",
        )
        BankAccount.objects.create(
            merchant=m3,
            account_number="5678901234567890",
            ifsc_code="SBIN0009876",
            account_holder_name="Rahul Patel",
            bank_name="State Bank of India",
        )
        # Credit history: 3 payments totaling ₹2,25,000
        credits_m3 = [
            (10000000, "Payment from FinCorp - API Integration", 18),
            (7500000, "Payment from HealthTech - Mobile App MVP", 10),
            (5000000, "Payment from RetailPro - E-commerce Plugin", 4),
        ]
        for amount, desc, days_ago in credits_m3:
            LedgerEntry.objects.create(
                merchant=m3,
                entry_type=LedgerEntry.EntryType.CREDIT,
                amount_paise=amount,
                description=desc,
                created_at=now - timedelta(days=days_ago),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"  Created merchant: {m3.name} (₹2,25,000 in credits)"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "\n✓ Seeded 3 merchants with credit history successfully!"
            )
        )
