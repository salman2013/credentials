"""
Tests for credentials service views.
"""
from __future__ import unicode_literals
import json

import ddt
from django.contrib.auth.models import Permission
from django.core.urlresolvers import reverse
from rest_framework.test import APITestCase
from testfixtures import LogCapture

from credentials.apps.api.serializers import UserCredentialSerializer
from credentials.apps.api.tests import factories
from credentials.apps.credentials.models import UserCredential


JSON_CONTENT_TYPE = 'application/json'
LOGGER_NAME = 'credentials.apps.credentials.issuers'
LOGGER_NAME_SERIALIZER = 'credentials.apps.api.serializers'


@ddt.ddt
class UserCredentialViewSetTests(APITestCase):
    """ Tests for GenerateCredentialView. """

    list_path = reverse("api:v1:usercredential-list")

    def setUp(self):
        super(UserCredentialViewSetTests, self).setUp()

        self.user = factories.UserFactory()
        self.client.force_authenticate(self.user)  # pylint: disable=no-member

        self.program_cert = factories.ProgramCertificateFactory()
        self.program_id = self.program_cert.program_id
        self.user_credential = factories.UserCredentialFactory.create(credential=self.program_cert)
        self.user_credential_attribute = factories.UserCredentialAttributeFactory.create(
            user_credential=self.user_credential)

    def _attempt_update_user_credential(self, data):
        """ Helper method that attempts to patch an existing credential object.

        Arguments:
          data (dict): Data to be converted to JSON and sent to the API.

        Returns:
          Response: HTTP response from the API.
        """
        # pylint: disable=no-member
        self.user.user_permissions.add(Permission.objects.get(codename="change_usercredential"))
        path = reverse("api:v1:usercredential-detail", args=[self.user_credential.id])
        return self.client.patch(path=path, data=json.dumps(data), content_type=JSON_CONTENT_TYPE)

    def test_get(self):
        """ Verify a single user credential is returned. """

        path = reverse("api:v1:usercredential-detail", args=[self.user_credential.id])
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, UserCredentialSerializer(self.user_credential).data)

    def test_list_without_username(self):
        """ Verify a list end point of user credentials will work only with
        username filter. Otherwise it will return 400.
        """
        response = self.client.get(self.list_path)
        self.assertEqual(response.status_code, 400)

    def test_partial_update(self):
        """ Verify the only status field can be updated. """
        data = {
            'id': self.user_credential.id,
            'status': UserCredential.REVOKED,
            'download_url': self.user_credential.download_url + 'test'
        }

        response = self._attempt_update_user_credential(data)
        self.assertEqual(response.status_code, 200)

        user_credential = UserCredential.objects.get(id=self.user_credential.id)
        self.assertEqual(user_credential.status, data["status"])
        self.assertEqual(user_credential.download_url, self.user_credential.download_url)

    def test_partial_update_authentication(self):
        """ Verify that patch endpoint allows only authorized users to update
        user credential.
        """
        self.client.logout()
        data = {
            "id": self.user_credential.id,
            "download_url": "dummy-url",
        }

        path = reverse("api:v1:usercredential-detail", args=[self.user_credential.id])
        response = self.client.patch(path=path, data=json.dumps(data), content_type=JSON_CONTENT_TYPE)
        self.assertEqual(response.status_code, 403)

    def _attempt_create_user_credentials(self, data):
        """ Helper method that attempts to create user credentials.

        Arguments:
          data (dict): Data to be converted to JSON and sent to the API.

        Returns:
          Response: HTTP response from the API.
        """
        # pylint: disable=no-member
        self.user.user_permissions.add(Permission.objects.get(codename="add_usercredential"))
        path = self.list_path
        return self.client.post(path=path, data=json.dumps(data), content_type=JSON_CONTENT_TYPE)

    @ddt.data(
        ("username", "", "This field may not be blank."),
        ("credential", "", "Credential ID is missing."),
        ("credential", {"program_id": ""}, "Credential ID is missing."),
        ("credential", {"course_id": ""}, "Credential ID is missing."),
    )
    @ddt.unpack
    def test_create_with_empty_fields(self, field_name, value, err_msg):
        """ Verify no UserCredential is created, and HTTP 400 is returned, if
        required fields are missing.
        """
        data = {
            "username": "test_user",
            "credential": {"program_id": self.program_id},
            "attributes": [
                {
                    "namespace": "testing",
                    "name": "grade",
                    "value": "0.8"
                }
            ]
        }
        data.update({field_name: value})
        response = self._attempt_create_user_credentials(data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data.get(field_name),
            [err_msg]
        )

    @ddt.data(
        "username",
        "credential",
        "attributes",
    )
    def test_create_with_missing_fields(self, field_name):
        """ Verify no UserCredential is created, and HTTP 400 is returned, if
        required fields are missing.
        """
        username = "test_user"
        data = {
            "username": username,
            "credential": {"program_id": self.program_id},
            "attributes": [
                {
                    "namespace": "testing",
                    "name": "grade",
                    "value": "0.8"
                }
            ]
        }
        del data[field_name]
        response = self._attempt_create_user_credentials(data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data.get(field_name),
            ['This field is required.']
        )

    def test_create_with_programcertificate(self):
        """ Verify the endpoint supports issuing a new ProgramCertificate credential. """

        program_certificate = factories.ProgramCertificateFactory()
        username = 'user2'
        data = {
            "username": username,
            "credential": {
                "program_id": program_certificate.program_id
            },
            "attributes": [
                {
                    "namespace": self.user_credential_attribute.namespace,
                    "name": self.user_credential_attribute.name,
                    "value": self.user_credential_attribute.value
                },
                {
                    "namespace": "testing",
                    "name": "grade",
                    "value": "0.8"
                }
            ]
        }
        response = self._attempt_create_user_credentials(data)
        self.assertEqual(response.status_code, 201)
        user_credential = UserCredential.objects.get(username=username)
        self.assertEqual(json.loads(response.content), UserCredentialSerializer(user_credential).data)

    def test_create_authentication(self):
        """ Verify that the create endpoint of user credential does not allow
        the unauthorized users to create a new user credential for the program.
        """
        self.client.logout()
        path = self.list_path
        response = self.client.post(path=path, data={}, content_type=JSON_CONTENT_TYPE)

        self.assertEqual(response.status_code, 403)

    def test_create_with_duplicate_attributes(self):
        """ Verify no UserCredential is created, and HTTP 400 is returned, if
        there are duplicated attributes.
        """
        username = 'test_user'
        data = {
            "username": username,
            "credential": {"program_id": self.program_id},
            "attributes": [
                {
                    "namespace": "white",
                    "name": "grade",
                    "value": "0.5"
                },
                {
                    "namespace": "dummyspace",
                    "name": "grade",
                    "value": "0.6"
                },
                {
                    "namespace": "white",
                    "name": "grade",
                    "value": "0.8"
                },
                {
                    "namespace": "white",
                    "name": "grade",
                    "value": "0.8"
                }
            ]
        }

        response = self._attempt_create_user_credentials(data)
        self.assertEqual(response.data, {'attributes': ['Attributes cannot be duplicated.']})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserCredential.objects.filter(username=username).exists())

    def test_create_with_empty_attributes(self):
        """ Verify no UserCredential is created, and HTTP 400 is returned, if
        there are some attributes are null.
        """
        username = 'test_user_duplicate_attr'
        data = {
            "username": username,
            "credential": {"program_id": self.program_id},
            "attributes": [
                {
                    "namespace": "white",
                    "name": "grade",
                    "value": "0.5"
                },
                {
                    "namespace": "",
                    "name": "grade",
                    "value": "0.8"
                }
            ]
        }
        response = self._attempt_create_user_credentials(data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserCredential.objects.filter(username=username).exists())
        self.assertEqual(
            response.data.get('attributes')[1]['namespace'][0],
            'This field may not be blank.'
        )

    def test_create_with_existing_usercredential(self):
        """ Verify that, if a user has already been issued a credential, further
        attempts to issue the same credential will NOT create a new credential
        and will NOT modify the existing credential.
        """
        username = 'test_user'
        data = {
            "username": username,
            "credential": {
                "program_id": self.program_id
            },
            "attributes": [
                {
                    "namespace": "white",
                    "name": "grade",
                    "value": "0.5"
                }
            ]
        }

        user_credential_1 = factories.UserCredentialFactory.create(username=username, credential=self.program_cert)

        # 2nd attempt to create credential with attributes.
        msg = 'User [{username}] already has a credential for program [{program_id}].'.format(
            username=username,
            program_id=self.program_id
        )

        # Verify log is captured.
        with LogCapture(LOGGER_NAME) as l:
            response = self._attempt_create_user_credentials(data)
            l.check((LOGGER_NAME, 'WARNING', msg))

        self.assertEqual(response.status_code, 201)
        user_credential_2 = UserCredential.objects.get(username=username)
        self.assertEqual(user_credential_1, user_credential_2)

    def test_list_with_username_filter(self):
        """ Verify the list endpoint supports filter data by username."""
        factories.UserCredentialFactory(username="dummy-user")
        path = self.list_path + "?username=" + self.user_credential.username

        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

        # after filtering it is only one related record
        expected = UserCredentialSerializer(self.user_credential).data
        self.assertEqual(response.data, {'count': 1, 'next': None, 'previous': None, 'results': [expected]})

    def test_list_with_status_filter(self):
        """ Verify the list endpoint supports filtering by status."""
        factories.UserCredentialFactory.create_batch(2, status="revoked", username=self.user_credential.username)
        path = self.list_path + "?status={}" + self.user_credential.status

        response = self.client.get(path)
        self.assertEqual(response.status_code, 400)

        # username and status will return the data.
        path = self.list_path + "?username={user}&status={status}".format(
            user=self.user_credential.username,
            status=UserCredential.AWARDED)
        response = self.client.get(path)

        # after filtering it is only one related record
        expected = UserCredentialSerializer(self.user_credential).data
        self.assertEqual(
            json.loads(response.content),
            {'count': 1, 'next': None, 'previous': None, 'results': [expected]}
        )

    def test_create_with_non_existing_credential(self):
        """ Verify no UserCredential is created, and HTTP 400 is return if credential
        id does not exists in db.
        """
        username = 'test_user'
        cred_id = 10
        data = {
            "username": username,
            "credential": {
                "program_id": cred_id
            },
            "attributes": [
            ]
        }

        msg = "Credential ID [{cred_id}] for [ProgramCertificate matching query does not exist.]".format(
            cred_id=cred_id
        )

        # Verify log is captured.
        with LogCapture(LOGGER_NAME_SERIALIZER) as l:
            response = self._attempt_create_user_credentials(data)
            l.check((LOGGER_NAME_SERIALIZER, 'ERROR', msg))

        self.assertEqual(response.status_code, 400)
