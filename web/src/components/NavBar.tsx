import { Link, useLocation } from "react-router-dom";

const NavBar = () => {
  const location = useLocation();
  const isPlanner = location.pathname.startsWith("/planner");

  return (
    <header className="nav">
      <div className="nav__brand">
        <span className="nav__logo">A</span>
        <Link className="nav__title" to="/">AlpScheduler</Link>
      </div>
      {!isPlanner && (
        <>
          <nav className="nav__links">
            <Link to="/planner" className="active">Trip Planner</Link>
            <a href="#guide">City Guides</a>
            <a href="#getting-started">Getting Started</a>
          </nav>
          <Link className="nav__cta" to="/planner">Start Planning</Link>
        </>
      )}
    </header>
  );
};

export default NavBar;
