import './styles.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { DrawerProvider } from './components/Drawers.jsx';
import { ToastProvider } from './components/overlays.jsx';
import Layout from './Layout.jsx';
import Accounts from './pages/Accounts.jsx';
import Dashboard from './pages/Dashboard.jsx';
import DataReview from './pages/DataReview.jsx';
import Insights from './pages/Insights.jsx';
import NewEntry from './pages/NewEntry.jsx';
import Opportunities from './pages/Opportunities.jsx';
import Pipeline from './pages/Pipeline.jsx';
import Team from './pages/Team.jsx';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10000, refetchOnWindowFocus: false, retry: 1, placeholderData: (prev) => prev } },
});

// Drawers need router (navigation), toasts and the query client, so they sit inside the layout route.
const Shell = () => (
  <DrawerProvider>
    <Layout />
  </DrawerProvider>
);

const router = createBrowserRouter([
  {
    path: '/', element: <Shell />, children: [
      { index: true, element: <Dashboard /> },
      { path: 'pipeline', element: <Pipeline /> },
      { path: 'opportunities', element: <Opportunities /> },
      { path: 'accounts', element: <Accounts /> },
      { path: 'team', element: <Team /> },
      { path: 'new', element: <NewEntry /> },
      { path: 'insights', element: <Insights /> },
      { path: 'data', element: <DataReview /> },
    ],
  },
]);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
