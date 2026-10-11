import { Modal } from 'antd';
import type { ModalProps } from 'antd';

type StableModalProps = Omit<ModalProps, 'centered'> & { size?: 'standard' | 'compact' };

/** Keep the frame and actions in place while the body loads, expands or scrolls. */
export function StableModal({ size = 'standard', className = '', title, ...props }: StableModalProps) {
  return <Modal destroyOnHidden {...props} centered className={`stable-modal stable-modal--${size} ${className}`}
    title={typeof title === 'string' ? <span className="stable-modal-title" title={title}>{title}</span> : title} />;
}
