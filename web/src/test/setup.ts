/**
 * Vitest setup, loaded before every test file.
 *
 * Adds jest-dom's DOM matchers (`toBeChecked`, `toBeDisabled`, …) and clears
 * the DOM between tests so one test's render cannot leak into the next.
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)
