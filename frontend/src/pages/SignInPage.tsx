import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import SignIn from "../components/Auth/SignIn";
import { useUserSessionStore } from "../store/userSession";

export default function SignInPage() {
  const { isUserLoggedIn } = useUserSessionStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (isUserLoggedIn) navigate("/tracks");
  }, [isUserLoggedIn, navigate]);

  return <SignIn />;
}
