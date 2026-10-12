import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from policy import Provider, Status, approve, dispatch, submit

class TestPolicy(unittest.TestCase):
    def job(self, provider=Provider.LOCAL):
        return submit("job-1", "requester", provider, Decimal("1000"))
    def test_requires_approval(self):
        with self.assertRaises(PermissionError):
            dispatch(self.job(), Provider.LOCAL, "worker")
    def test_approved_local(self):
        j=self.job()
        approve(j,"admin","approval-1",(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),Decimal("1000"))
        self.assertTrue(dispatch(j,Provider.LOCAL,"worker"))
        self.assertEqual(j.status,Status.DISPATCHED)
    def test_provider_is_pinned(self):
        j=self.job()
        approve(j,"admin","approval-1",(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),Decimal("1000"))
        with self.assertRaises(PermissionError):
            dispatch(j,Provider.RENTED,"worker")
    def test_budget_cap(self):
        j=self.job(Provider.RENTED)
        with self.assertRaises(PermissionError):
            approve(j,"admin","approval-1",(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),Decimal("999"))
    def test_no_self_approval(self):
        j=self.job()
        with self.assertRaises(PermissionError):
            approve(j,"requester","approval-1",(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),Decimal("1000"))
    def test_no_repeat_dispatch(self):
        j=self.job()
        approve(j,"admin","approval-1",(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),Decimal("1000"))
        dispatch(j,Provider.LOCAL,"worker")
        with self.assertRaises(PermissionError):
            dispatch(j,Provider.LOCAL,"worker")
if __name__=="__main__": unittest.main()
