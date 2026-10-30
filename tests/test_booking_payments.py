"""Integration checks use a disposable SQLite database, never salon records."""
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="salon-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(TEST_DIRECTORY.name) / 'test.db'}"
os.environ["APP_ENV"] = "development"
os.environ["SESSION_HTTPS_ONLY"] = "false"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from PIL import Image

from app.database import Base, SessionLocal, engine, migrate_payments, migrate_service_images
from app.main import app
from app.models import Appointment, BusinessHours, Customer, Service, Setting
from app.payments import price_in_cents
from app.security import hash_password
from app.settings_store import set_setting
from app.slots import now_local


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def tearDownModule():
    engine.dispose()
    TEST_DIRECTORY.cleanup()


class BookingPaymentsTests(unittest.TestCase):
    def test_admin_can_book_and_cannot_overlap_public_booking(self):
        self.login_admin()
        page = self.client.get(f"/admin/agendar?service_id={self.service_id}&day={self.day}")
        self.assertEqual(page.status_code, 200)
        self.assertIn('value="09:00"', page.text)
        data = dict(csrf=csrf(page), service_id=self.service_id, day=str(self.day),
                    start_time="09:00", client_name="Cliente pela administradora",
                    client_phone="(11) 98888-7777", notes="Preferência de cor")
        result = self.client.post("/admin/agendar", data=data, follow_redirects=False)
        self.assertEqual(result.status_code, 303)
        agenda = self.client.get(result.headers["location"])
        self.assertIn("Agendamento confirmado", agenda.text)
        self.assertIn("Cliente pela administradora", agenda.text)
        result = self.client.post("/admin/agendar", data=data)
        self.assertEqual(result.status_code, 400)
        self.assertIn("não está mais disponível", result.text)
        self.assertIn('value="Cliente pela administradora"', result.text)
        self.assertEqual(self.book().status_code, 400)
        with SessionLocal() as db:
            booking = db.query(Appointment).one()
            self.assertEqual(booking.client_phone, "11988887777")
            self.assertEqual(booking.payment_status, "pendente")
            self.assertEqual(booking.amount_cents, price_in_cents(booking.service.price))

    def test_admin_booking_requires_login_csrf_and_valid_data(self):
        result = self.client.get("/admin/agendar", follow_redirects=False)
        self.assertEqual(result.headers["location"], "/admin/login")
        self.login_admin()
        page = self.client.get("/admin/agendar")
        data = dict(service_id=self.service_id, day=str(self.day), start_time="09:00",
                    client_name="Cliente", client_phone="11988887777")
        self.assertEqual(self.client.post("/admin/agendar", data={**data, "csrf": "invalid"}).status_code, 403)
        for invalid in ({"client_phone": "1"}, {"client_name": " "}, {"day": "2000-01-01"},
                        {"start_time": "03:00"}, {"service_id": "invalid"}):
            result = self.client.post("/admin/agendar", data={**data, "csrf": csrf(page), **invalid})
            self.assertEqual(result.status_code, 400)
        with SessionLocal() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_agenda_filters_keep_history_and_do_not_modify_bookings(self):
        self.assertEqual(self.book(client_name="Cliente futura").status_code, 303)
        with SessionLocal() as db:
            future = db.query(Appointment).one()
            today = Appointment(
                service_id=self.service_id, client_name="Cliente de hoje", client_phone="11988887777",
                day=now_local().date(), start_time=future.start_time, end_time=future.end_time,
                created_at=now_local().replace(tzinfo=None), status="confirmado", amount_cents=3500,
            )
            historical = Appointment(
                service_id=self.service_id, client_name="Cliente antiga", client_phone="11988887777",
                day=now_local().date() - timedelta(days=2), start_time=future.start_time, end_time=future.end_time,
                created_at=now_local().replace(tzinfo=None), status="cancelado", amount_cents=3500,
            )
            db.add_all([today, historical])
            db.commit()
            snapshot = [(a.id, a.client_name, a.day, a.status, a.amount_cents) for a in db.query(Appointment).order_by(Appointment.id)]
        self.login_admin()
        result = self.client.get("/admin")
        self.assertIn("Cliente de hoje", result.text)
        self.assertNotIn("Cliente futura", result.text)
        self.assertNotIn("Cliente antiga", result.text)
        result = self.client.get("/admin?periodo=proximos")
        self.assertIn("Cliente futura", result.text)
        self.assertNotIn("Cliente antiga", result.text)
        result = self.client.get("/admin?periodo=todos&status=cancelado&busca=antiga")
        self.assertIn("Cliente antiga", result.text)
        self.assertNotIn("Cliente futura", result.text)
        self.assertIn("Cancelados (1)", result.text)
        # Search wildcards are literal, never a way to select every record.
        self.assertNotIn("Cliente futura", self.client.get("/admin?periodo=todos&busca=%25").text)
        result = self.client.get("/admin?periodo=todos")
        for name in ("Cliente de hoje", "Cliente futura", "Cliente antiga"):
            self.assertIn(name, result.text)
        with SessionLocal() as db:
            self.assertEqual(snapshot, [(a.id, a.client_name, a.day, a.status, a.amount_cents) for a in db.query(Appointment).order_by(Appointment.id)])

    def setUp(self):
        Base.metadata.drop_all(engine)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.day = now_local().date() + timedelta(days=1)
        while self.day.weekday() == 6:
            self.day += timedelta(days=1)
        with SessionLocal() as db:
            self.service_id = db.query(Service).filter(Service.name == "Manicure simples").one().id
            set_setting(db, "owner_whatsapp", "")
            db.commit()

    def configure_pix(self):
        with SessionLocal() as db:
            set_setting(db, "pix_key", "fixture@example.invalid")
            set_setting(db, "pix_recipient", "Titular de teste")
            db.commit()

    def test_database_environment_accepts_existing_vercel_name(self):
        from app.config import database_url_from_environment
        with patch.dict(os.environ, {"DATABASE_URL": "", "URL_DO_BANCO_DE_DADOS": " postgresql://test.invalid/salon "}):
            self.assertEqual(database_url_from_environment(), "postgresql://test.invalid/salon")
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///explicit.db", "URL_DO_BANCO_DE_DADOS": "postgresql://test.invalid/salon"}):
            self.assertEqual(database_url_from_environment(), "sqlite:///explicit.db")

    def test_login_csrf_recovery_and_session_lifecycle(self):
        from app.config import SESSION_MAX_AGE
        from app.routers.admin import ADMIN_LOGIN_FAILURES
        ADMIN_LOGIN_FAILURES.clear()
        token = csrf(self.client.get("/admin/login"))
        self.client.cookies.clear()
        result = self.client.post("/admin/login", data={"csrf": token, "password": "admin123"})
        self.assertEqual(result.status_code, 403)
        self.assertIn("text/html", result.headers["content-type"])
        self.assertIn("Sua sessão de acesso expirou", result.text)
        self.assertNotIn("admin123", result.text)
        self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 303)
        token = csrf(result)
        for password in ("incorrect", "another-incorrect-password"):
            result = self.client.post("/admin/login", data={"csrf": token, "password": password})
            self.assertEqual(result.status_code, 401)
            self.assertIn("Senha incorreta", result.text)
        result = self.client.post("/admin/login", data={"csrf": token, "password": "admin123"}, follow_redirects=False)
        self.assertEqual(result.status_code, 303)
        self.assertEqual(result.headers["location"], "/admin")
        cookie = result.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        for _ in range(2):
            result = self.client.get("/admin")
            self.assertEqual(result.status_code, 200)
        token = csrf(result)
        self.assertEqual(self.client.post("/admin/sair", data={"csrf": token}, follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 303)
        self.login_admin()
        import time
        with patch("time.time", return_value=time.time() + SESSION_MAX_AGE + 1):
            self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 303)

    def test_login_rejects_missing_invalid_and_unicode_csrf_as_html(self):
        for value in (None, "invalid", "inválido"):
            self.client.get("/admin/login")
            data = {"password": "admin123"}
            if value is not None:
                data["csrf"] = value
            result = self.client.post("/admin/login", data=data)
            self.assertEqual(result.status_code, 403)
            self.assertIn("text/html", result.headers["content-type"])

    def test_login_with_mobile_user_agent(self):
        self.client.headers["user-agent"] = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36"
        self.login_admin()
        self.assertEqual(self.client.get("/admin").status_code, 200)

    def test_card_checkout_policy_csrf_and_submission(self):
        with patch("app.routers.public.MERCADOPAGO_ENABLED", True):
            checkout = self.existing_card_checkout()
            self.assertEqual(checkout.status_code, 200)
            policy = checkout.headers["content-security-policy"]
            self.assertIn("https://sdk.mercadopago.com", policy)
            self.assertIn("frame-src https://*.mercadopago.com", policy)
            self.assertNotIn("sdk.mercadopago.com", self.client.get("/admin/login").headers["content-security-policy"])
            token = re.search(r'data-csrf="([^"]+)"', checkout.text).group(1)
            endpoint = re.search(r'data-endpoint="([^"]+)"', checkout.text).group(1)
            with patch("app.routers.public.create_mercadopago_card_payment", return_value={"id": 123, "status": "approved", "status_detail": "accredited"}) as provider:
                self.assertEqual(self.client.post(endpoint, json={}, headers={"X-CSRF-Token": "invalid"}).status_code, 403)
                provider.assert_not_called()
                response = self.client.post(endpoint, json={"token": "test-only"}, headers={"X-CSRF-Token": token})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "approved")
                self.assertTrue(provider.call_args.args[3])
                self.client.post(endpoint, json={}, headers={"X-CSRF-Token": token})
                provider.assert_called_once()
            with SessionLocal() as db:
                appointment = db.query(Appointment).one()
                self.assertEqual(appointment.payment_status, "pago")
                self.assertEqual(appointment.mercadopago_payment_id, "123")

    def test_card_rejection_allows_retry_and_timeout_prevents_resubmission(self):
        from app.payments import MercadoPagoRequestError
        with patch("app.routers.public.MERCADOPAGO_ENABLED", True):
            checkout = self.existing_card_checkout()
            token = re.search(r'data-csrf="([^"]+)"', checkout.text).group(1)
            endpoint = re.search(r'data-endpoint="([^"]+)"', checkout.text).group(1)
            with patch("app.routers.public.create_mercadopago_card_payment", side_effect=MercadoPagoRequestError(400, "bad_request", [])):
                self.assertEqual(self.client.post(endpoint, json={}, headers={"X-CSRF-Token": token}).status_code, 502)
            with patch("app.routers.public.create_mercadopago_card_payment", side_effect=RuntimeError("Verificando pagamento")) as provider:
                self.assertEqual(self.client.post(endpoint, json={}, headers={"X-CSRF-Token": token}).status_code, 504)
                result = self.client.post(endpoint, json={}, headers={"X-CSRF-Token": token})
                self.assertEqual(result.json()["status"], "processing")
                provider.assert_called_once()


    def test_restart_preserves_owners_catalog_settings_hours_and_bookings(self):
        self.assertEqual(self.book().status_code, 303)
        with SessionLocal() as db:
            service = db.get(Service, self.service_id)
            service.name = "Fibra personalizada pela dona"
            service.category = "Minha categoria"
            service.description = "Descrição cadastrada no salão"
            service.price = 187.50
            service.duration_minutes = 135
            service.active = False
            service.image_data = b"existing-photo"
            service.image_revision = "existing-revision"
            hours = db.query(BusinessHours).filter_by(weekday=0).one()
            hours.is_open = False
            set_setting(db, "salon_name", "Salão da minha mãe")
            set_setting(db, "owner_whatsapp", "11977776666")
            db.commit()
            password = db.get(Setting, "admin_password_hash").value
            service_count = db.query(Service).count()
            booking = db.query(Appointment).one()
            booking_snapshot = (booking.id, booking.service_id, booking.day, booking.start_time, booking.amount_cents)

        # Exercise the real startup path twice against an already customized database.
        for _ in range(2):
            with TestClient(app):
                pass
        with SessionLocal() as db:
            service = db.get(Service, self.service_id)
            self.assertEqual((service.name, service.category, service.description, service.price,
                              service.duration_minutes, service.active, service.image_data, service.image_revision),
                             ("Fibra personalizada pela dona", "Minha categoria", "Descrição cadastrada no salão",
                              187.50, 135, False, b"existing-photo", "existing-revision"))
            self.assertEqual(db.query(Service).count(), service_count)
            self.assertFalse(db.query(BusinessHours).filter_by(weekday=0).one().is_open)
            self.assertEqual(db.get(Setting, "salon_name").value, "Salão da minha mãe")
            self.assertEqual(db.get(Setting, "owner_whatsapp").value, "11977776666")
            self.assertEqual(db.get(Setting, "admin_password_hash").value, password)
            booking = db.query(Appointment).one()
            self.assertEqual((booking.id, booking.service_id, booking.day, booking.start_time, booking.amount_cents),
                             booking_snapshot)

    def existing_card_checkout(self):
        """Legacy card records remain usable after cards were removed from new bookings."""
        self.assertEqual(self.book().status_code, 303)
        with SessionLocal() as db:
            appointment = db.query(Appointment).one()
            appointment.payment_method = "cartao"
            db.commit()
            appointment_id = appointment.id
        return self.client.get(f"/pagamento/cartao/{appointment_id}")

    def book(self, **overrides):
        form = self.client.get("/agendar")
        values = dict(
            csrf=csrf(form), service_id=self.service_id, day=self.day.isoformat(),
            start_time="09:00", client_name="Cliente de teste", client_phone="11988887777",
            payment_method="no_local",
        )
        values.update(overrides)
        return self.client.post("/agendar", data=values, follow_redirects=False)

    def login_admin(self):
        token = csrf(self.client.get("/admin/login"))
        response = self.client.post("/admin/login", data={"csrf": token, "password": "admin123"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        return csrf(self.client.get("/admin"))

    def test_pix_disabled_until_configured_and_invalid_method_rejected(self):
        self.assertIn('value="pix"  disabled', self.client.get("/agendar").text)
        self.assertEqual(self.book(payment_method="pix").status_code, 400)
        self.assertEqual(self.book(payment_method="cartao").status_code, 400)
        with SessionLocal() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_booking_csrf_and_duplicate_slot(self):
        self.assertEqual(self.book(csrf="invalid").status_code, 403)
        self.assertEqual(self.book().status_code, 303)
        duplicate = self.book()
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("não está mais disponível", duplicate.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(Appointment).count(), 1)

    def test_pay_at_establishment_remains_available_when_pix_is_configured(self):
        self.configure_pix()
        form = self.client.get("/agendar")
        self.assertRegex(form.text, r'value="no_local"\s+checked')
        result = self.book(payment_method="no_local")
        self.assertEqual(result.status_code, 303)
        confirmation = self.client.get(result.headers["location"])
        self.assertIn("Você escolheu fazer o pagamento no estabelecimento", confirmation.text)
        self.assertNotIn('id="pix-key"', confirmation.text)
        with SessionLocal() as db:
            appointment = db.query(Appointment).one()
            self.assertEqual(appointment.status, "confirmado")
            self.assertEqual(appointment.payment_method, "no_local")
            self.assertEqual(appointment.payment_status, "pendente")
            self.assertEqual(appointment.pix_key, "")
        slots = self.client.get(f"/api/horarios?servico={self.service_id}&dia={self.day.isoformat()}").json()["slots"]
        self.assertNotIn("09:00", slots)

    def test_pix_snapshot_reload_and_private_confirmation(self):
        self.configure_pix()
        response = self.book(payment_method="pix", amount_cents="1", payment_status="pago")
        self.assertEqual(response.status_code, 303)
        location = response.headers["location"]
        with SessionLocal() as db:
            booking = db.query(Appointment).one()
            self.assertEqual(booking.amount_cents, 3500)
            self.assertEqual(booking.payment_status, "pendente")
            booking.service.price = 99
            set_setting(db, "pix_key", "changed@example.invalid")
            set_setting(db, "pix_recipient", "Outro titular")
            db.commit()
        page = self.client.get(location)
        self.assertEqual(page.status_code, 200)
        self.assertIn("R$ 35,00", page.text)
        self.assertIn("fixture@example.invalid", page.text)
        self.assertNotIn("changed@example.invalid", page.text)
        self.assertIn("Aguardando conferência", page.text)
        self.assertEqual(page.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get(location).status_code, 200)
        self.assertEqual(TestClient(app).get(location).status_code, 404)
        self.assertEqual(self.client.get("/agendamentos/999999").status_code, 404)

    def test_only_admin_can_record_payment_and_requires_conference(self):
        self.configure_pix()
        self.book(payment_method="pix")
        token = csrf(self.client.get("/agendar"))
        endpoint = "/admin/agendamentos/1/pagamento"
        result = self.client.post(endpoint, data={"csrf": token, "received": "conferido"}, follow_redirects=False)
        self.assertEqual(result.headers["location"], "/admin/login")
        token = self.login_admin()
        self.assertEqual(self.client.post(endpoint, data={"csrf": "invalid", "received": "conferido"}).status_code, 403)
        self.assertEqual(self.client.post(endpoint, data={"csrf": token}).status_code, 400)
        self.assertEqual(self.client.post(endpoint, data={"csrf": token, "received": "conferido"}, follow_redirects=False).status_code, 303)
        with SessionLocal() as db:
            original_stamp = db.get(Appointment, 1).payment_confirmed_at
            self.assertIsNotNone(original_stamp)
        self.client.post(endpoint, data={"csrf": token, "received": "conferido"})
        with SessionLocal() as db:
            self.assertEqual(db.get(Appointment, 1).payment_status, "pago")
            self.assertEqual(db.get(Appointment, 1).payment_confirmed_at, original_stamp)

    def test_cancelled_reservation_hides_payment_instructions(self):
        self.configure_pix()
        response = self.book(payment_method="pix")
        location = response.headers["location"]
        with SessionLocal() as db:
            db.get(Appointment, 1).status = "cancelado"
            db.commit()
        page = self.client.get(location)
        self.assertIn("Não efetue o pagamento", page.text)
        self.assertNotIn('id="pix-key"', page.text)
        token = self.login_admin()
        self.assertEqual(self.client.post("/admin/agendamentos/1/pagamento", data={"csrf": token, "received": "conferido"}).status_code, 400)

    def test_customer_accounts_are_disabled_and_old_records_preserved(self):
        with SessionLocal() as db:
            customer = Customer(
                name="Cliente de teste", email="customer@example.invalid", phone="11988887777",
                password_hash=hash_password("local-test-password"), created_at=datetime.now(),
                email_verified_at=datetime.now(),
            )
            db.add(customer)
            db.commit()
            customer_id = customer.id
        for path in ("/cliente/login", "/cliente/cadastro", "/cliente/minha-conta", "/cliente/verificar?token=test"):
            self.assertEqual(self.client.get(path).status_code, 404)
        for path in ("/cliente/login", "/cliente/cadastro", "/cliente/verificar", "/cliente/reenviar-confirmacao"):
            self.assertEqual(self.client.post(path, data={}).status_code, 404)
        page = self.client.get("/agendar")
        self.assertNotIn('value="Cliente de teste"', page.text)
        self.assertNotIn("/cliente/", page.text)
        self.assertNotIn("Minha conta", page.text)
        self.assertEqual(self.book(customer_id=customer_id).status_code, 303)
        with SessionLocal() as db:
            self.assertIsNone(db.query(Appointment).one().customer_id)
            self.assertIsNotNone(db.get(Customer, customer_id))
        self.assertEqual(self.client.get("/agendamentos/1").status_code, 200)
        self.assertEqual(self.client.get("/login", follow_redirects=False).headers["location"], "/admin/login")
        self.assertNotIn('href="/admin', self.client.get("/").text)
        self.assertNotIn("Área da dona", self.client.get("/").text)

    @staticmethod
    def photo_bytes(color="plum", size=(32, 24)):
        output = BytesIO()
        Image.new("RGB", size, color).save(output, format="PNG")
        return output.getvalue()

    def service_form(self, token, **overrides):
        data = dict(csrf=token, name="Serviço com foto", category="Unhas", description="Foto ilustrativa", price="35.00", duration_minutes="40", active="on")
        data.update(overrides)
        return data

    def test_service_photo_upload_replace_preserve_and_remove(self):
        token = self.login_admin()
        endpoint = f"/admin/servicos/{self.service_id}"
        data = self.service_form(token)
        response = self.client.post(endpoint, data=data, files={"image": ("foto.png", self.photo_bytes(size=(2000, 1000)), "image/png")}, follow_redirects=False)
        self.assertEqual(response.headers["location"], "/admin/servicos")
        with SessionLocal() as db:
            service = db.get(Service, self.service_id)
            revision = service.image_revision
            photo = service.image_data
        with Image.open(BytesIO(photo)) as normalized:
            self.assertEqual(normalized.format, "JPEG")
            self.assertEqual(normalized.size, (1600, 800))
            self.assertFalse(normalized.getexif())
        url = f"/media/servicos/{self.service_id}/{revision}.jpg"
        self.assertIn(url, self.client.get("/").text)
        public_client = TestClient(app)
        self.assertEqual(public_client.get(url).headers["content-type"], "image/jpeg")
        self.assertEqual(public_client.get(url).content, photo)
        self.assertIn("Foto exibida no catálogo", self.client.get("/admin/servicos").text)
        self.client.post(endpoint, data=data)
        with SessionLocal() as db:
            self.assertEqual(db.get(Service, self.service_id).image_revision, revision)
        self.client.post(endpoint, data=data, files={"image": ("outra.png", self.photo_bytes("blue"), "image/png")})
        with SessionLocal() as db:
            changed_revision = db.get(Service, self.service_id).image_revision
        self.assertNotEqual(changed_revision, revision)
        self.assertEqual(public_client.get(url).status_code, 404)
        self.client.post(endpoint, data={**data, "remove_image": "on"})
        with SessionLocal() as db:
            service = db.get(Service, self.service_id)
            self.assertEqual(service.image_revision, "")
            self.assertIsNone(service.image_data)
        self.assertEqual(public_client.get(f"/media/servicos/{self.service_id}/{changed_revision}.jpg").status_code, 404)

    def test_service_photo_requires_owner_and_csrf(self):
        token = csrf(self.client.get("/agendar"))
        files = {"image": ("foto.png", self.photo_bytes(), "image/png")}
        response = self.client.post(f"/admin/servicos/{self.service_id}", data=self.service_form(token), files=files, follow_redirects=False)
        self.assertEqual(response.headers["location"], "/admin/login")
        self.login_admin()
        self.assertEqual(self.client.post(f"/admin/servicos/{self.service_id}", data=self.service_form("invalid"), files=files).status_code, 403)
        with SessionLocal() as db:
            self.assertFalse(db.get(Service, self.service_id).image_revision)

    def test_invalid_images_leave_service_unchanged(self):
        token = self.login_admin()
        endpoint = f"/admin/servicos/{self.service_id}"
        self.client.post(endpoint, data=self.service_form(token), files={"image": ("foto.png", self.photo_bytes(), "image/png")})
        with SessionLocal() as db:
            revision = db.get(Service, self.service_id).image_revision
        invalid = [
            ("image.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "image/svg+xml"),
            ("fake.jpg", b"not an image", "image/jpeg"),
            ("big.jpg", b"x" * (5 * 1024 * 1024 + 1), "image/jpeg"),
            ("pixels.png", self.photo_bytes(size=(5000, 4001)), "image/png"),
        ]
        for upload in invalid:
            response = self.client.post(endpoint, data=self.service_form(token, name="Should not save"), files={"image": upload}, follow_redirects=False)
            self.assertEqual(response.headers["location"], "/admin/servicos?erro=imagem")
            with SessionLocal() as db:
                service = db.get(Service, self.service_id)
                self.assertEqual(service.name, "Serviço com foto")
                self.assertEqual(service.image_revision, revision)

    def test_create_service_with_optional_photo_and_hide_inactive_photo(self):
        token = self.login_admin()
        data = self.service_form(token)
        self.assertEqual(self.client.post("/admin/servicos", data=data, files={"image": ("foto.png", self.photo_bytes(), "image/png")}, follow_redirects=False).status_code, 303)
        with SessionLocal() as db:
            service = db.query(Service).filter(Service.name == "Serviço com foto").one()
            photo_url = f"/media/servicos/{service.id}/{service.image_revision}.jpg"
            service.active = False
            db.commit()
            count = db.query(Service).count()
        self.assertEqual(TestClient(app).get(photo_url).status_code, 404)
        self.assertEqual(self.client.get(photo_url).status_code, 200)
        self.assertEqual(self.client.get(photo_url).headers["cache-control"], "no-store")
        self.assertIn("erro=imagem", self.client.post("/admin/servicos", data=data, files={"image": ("fake.png", b"invalid", "image/png")}, follow_redirects=False).headers["location"])
        with SessionLocal() as db:
            self.assertEqual(db.query(Service).count(), count)

    def test_legacy_service_image_migration_is_repeatable(self):
        legacy_engine = create_engine(f"sqlite:///{Path(TEST_DIRECTORY.name) / 'legacy-services.db'}")
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text("CREATE TABLE services (id INTEGER PRIMARY KEY, name TEXT)"))
                connection.execute(text("INSERT INTO services VALUES (42, 'Legacy service')"))
            with patch("app.database.engine", legacy_engine):
                migrate_service_images()
                migrate_service_images()
            with legacy_engine.connect() as connection:
                row = connection.execute(text("SELECT * FROM services WHERE id=42")).mappings().one()
                self.assertEqual(row["name"], "Legacy service")
                self.assertIsNone(row["image_data"])
                self.assertEqual(row["image_revision"], "")
        finally:
            legacy_engine.dispose()

    def test_admin_settings_validate_pix_and_allow_disabling(self):
        token = self.login_admin()
        data = {"csrf": token, "salon_name": "Salão de teste", "pix_key": "fixture@example.invalid"}
        self.assertIn("erro=pix", self.client.post("/admin/config", data=data, follow_redirects=False).headers["location"])
        data["pix_recipient"] = "Titular de teste"
        self.assertEqual(self.client.post("/admin/config", data=data).status_code, 200)
        self.assertNotIn('value="pix"  disabled', self.client.get("/agendar").text)
        data.update(pix_key="", pix_recipient="")
        self.assertEqual(self.client.post("/admin/config", data=data).status_code, 200)
        self.assertIn('value="pix"  disabled', self.client.get("/agendar").text)

    def test_money_rounding(self):
        self.assertEqual(price_in_cents(35.29), 3529)
        self.assertEqual(price_in_cents(1.005), 101)

    def test_legacy_migration_preserves_rows_and_is_repeatable(self):
        legacy_engine = create_engine(f"sqlite:///{Path(TEST_DIRECTORY.name) / 'legacy.db'}")
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text("CREATE TABLE appointments (id INTEGER PRIMARY KEY, client_name TEXT)"))
                connection.execute(text("INSERT INTO appointments VALUES (42, 'Legacy')"))
            with patch("app.database.engine", legacy_engine):
                migrate_payments()
                migrate_payments()
            self.assertIn("amount_cents", {column["name"] for column in inspect(legacy_engine).get_columns("appointments")})
            with legacy_engine.connect() as connection:
                row = connection.execute(text("SELECT * FROM appointments WHERE id=42")).mappings().one()
                self.assertEqual(row["client_name"], "Legacy")
                self.assertIsNone(row["amount_cents"])
                self.assertEqual(row["payment_method"], "no_local")
        finally:
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
